"""Tests des cas d'usage cash : enrôlement agent, dépôt, retrait (BE-034 → BE-036)."""

from __future__ import annotations

from uuid import UUID

import pytest

from flash.application.cash.operations import (
    CancelCashWithdrawal,
    CancelWithdrawalCommand,
    ConfirmCashWithdrawal,
    ConfirmWithdrawalCommand,
    CreateCashDeposit,
    CreateCashDepositCommand,
    EnrollAgent,
    EnrollAgentCommand,
    InitiateCashWithdrawal,
    InitiateWithdrawalCommand,
    NotAnAgent,
)
from flash.application.services import AppServices
from flash.domain.cash.order import CashOrderStatus
from flash.domain.identity.pin import Pin
from flash.domain.identity.user import User
from flash.domain.ledger.transaction import sum_postings
from flash.domain.limits.limits import KycPolicy, LimitPolicy
from flash.domain.pricing.pricing import PricingService
from flash.domain.shared.errors import (
    InsufficientFunds,
    InvalidAccountState,
    InvalidInput,
    RecipientNotFound,
    WithdrawalCodeExpired,
    WithdrawalCodeInvalid,
)
from flash.domain.shared.identifiers import CountryCode, EntityId, Msisdn
from flash.domain.shared.money import XOF, Money
from flash.domain.wallet.wallet import Wallet
from flash.infrastructure.codes import PepperedWithdrawalCodes
from flash.infrastructure.limits import NullLimitCounter, build_limit_repository
from flash.infrastructure.pricing import build_pricing_repository
from tests.support.fakes import (
    FakePinHasher,
    FixedClock,
    InMemoryIdempotencyStore,
    RecordingEventPublisher,
    SeqIdGenerator,
)
from tests.support.repositories import InMemoryUnitOfWork

CI = CountryCode("CI")
AGENT_MSISDN = "+2250700000009"
CLIENT_MSISDN = "+2250700000001"
CODES = PepperedWithdrawalCodes("test-pepper-0123456789")


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def services(uow: InMemoryUnitOfWork, clock: FixedClock) -> AppServices:
    return AppServices(
        uow=lambda: uow,
        clock=clock,
        ids=SeqIdGenerator(),
        events=RecordingEventPublisher(),
        idempotency=InMemoryIdempotencyStore(),
    )


def _user(uow: InMemoryUnitOfWork, *, n: int, msisdn: str, balance: int = 0) -> User:
    user = User.register(
        user_id=EntityId(str(UUID(int=n))),
        country=CI,
        msisdn=Msisdn(msisdn),
        pin_hash=FakePinHasher().hash(Pin("1397")),
        now=FixedClock().now(),
    )
    user.activate(FixedClock().now())
    user.pull_events()
    uow.users.add(user)
    wallet = Wallet.open(
        wallet_id=EntityId(str(UUID(int=500 + n))),
        user_id=user.id,
        currency=XOF,
        now=FixedClock().now(),
    )
    if balance:
        wallet.credit(Money(balance, XOF), FixedClock().now())
    wallet.pull_events()
    uow.wallets.add(wallet)
    return user


def _enroll_agent(
    services: AppServices,
    uow: InMemoryUnitOfWork,
    *,
    float_cap: int,
    initial: int,
    bps: int = 100,
) -> str:
    _user(uow, n=9, msisdn=AGENT_MSISDN)
    view = EnrollAgent(services=services).execute(
        EnrollAgentCommand(
            user_id=str(UUID(int=9)),
            float_cap_minor=float_cap,
            initial_float_minor=initial,
            commission_bps=bps,
        )
    )
    return view.agent_id


class TestEnrollAgent:
    def test_enroll_creates_agent_with_initial_float(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        agent_id = _enroll_agent(services, uow, float_cap=1_000_000, initial=500_000)
        agent = uow.agents.get(EntityId(agent_id))
        assert agent is not None
        assert agent.float_available == Money(500_000, XOF)
        # écriture ledger d'approvisionnement équilibrée
        [topup] = [t for t in uow.ledger.transactions if t.kind.value == "AGENT_FLOAT_TOPUP"]
        assert topup.is_balanced

    def test_enroll_twice_rejected(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        _enroll_agent(services, uow, float_cap=1_000_000, initial=0)
        with pytest.raises(InvalidAccountState):
            EnrollAgent(services=services).execute(
                EnrollAgentCommand(user_id=str(UUID(int=9)), float_cap_minor=1_000_000)
            )


class TestCashDeposit:
    def test_deposit_credits_client_and_debits_agent_float(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _enroll_agent(services, uow, float_cap=1_000_000, initial=500_000)
        _user(uow, n=1, msisdn=CLIENT_MSISDN)

        receipt = CreateCashDeposit(
            services=services,
            limits=LimitPolicy(build_limit_repository(), NullLimitCounter()),
            kyc=KycPolicy(),
        ).execute(
            CreateCashDepositCommand(
                agent_user_id=str(UUID(int=9)),
                client_phone_number=CLIENT_MSISDN,
                amount_minor=40_000,
                idempotency_key="dep-key-0001",
            )
        )
        assert receipt.amount_minor == 40_000
        assert receipt.commission_minor == 400  # 1 %

        client_wallet = uow.wallets.get_for_user(EntityId(str(UUID(int=1))), XOF)
        assert client_wallet is not None
        assert client_wallet.available == Money(40_000, XOF)
        agent = uow.agents.get_by_user_id(EntityId(str(UUID(int=9))))
        assert agent is not None
        # float : 500 000 - 40 000 (décaissé) + 400 (commission) = 460 400
        assert agent.float_available == Money(460_400, XOF)

        [txn] = uow.ledger.get_by_reference(f"DEP-{receipt.order_id}")
        assert txn.is_balanced and sum_postings(txn.postings) == {"XOF": 0}

    def test_deposit_by_non_agent_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, n=1, msisdn=CLIENT_MSISDN)
        _user(uow, n=2, msisdn="+2250700000002")
        with pytest.raises(NotAnAgent):
            CreateCashDeposit(
                services=services,
                limits=LimitPolicy(build_limit_repository(), NullLimitCounter()),
                kyc=KycPolicy(),
            ).execute(
                CreateCashDepositCommand(
                    agent_user_id=str(UUID(int=2)),
                    client_phone_number=CLIENT_MSISDN,
                    amount_minor=1_000,
                    idempotency_key="dep-key-0002",
                )
            )

    def test_deposit_beyond_agent_float_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _enroll_agent(services, uow, float_cap=100_000, initial=50_000)
        _user(uow, n=1, msisdn=CLIENT_MSISDN)
        with pytest.raises(Exception, match="AGENT_FLOAT_TOO_LOW"):
            CreateCashDeposit(
                services=services,
                limits=LimitPolicy(build_limit_repository(), NullLimitCounter()),
                kyc=KycPolicy(),
            ).execute(
                CreateCashDepositCommand(
                    agent_user_id=str(UUID(int=9)),
                    client_phone_number=CLIENT_MSISDN,
                    amount_minor=60_000,
                    idempotency_key="dep-key-0003",
                )
            )


def _deposit_uc(services: AppServices) -> CreateCashDeposit:
    return CreateCashDeposit(
        services=services,
        limits=LimitPolicy(build_limit_repository(), NullLimitCounter()),
        kyc=KycPolicy(),
    )


def _initiate(services: AppServices, amount: int, key: str = "wdl-key-0001") -> tuple[str, str]:
    ticket = InitiateCashWithdrawal(
        services=services,
        pricing=PricingService(build_pricing_repository()),
        limits=LimitPolicy(build_limit_repository(), NullLimitCounter()),
        kyc=KycPolicy(),
        codes=CODES,
    ).execute(
        InitiateWithdrawalCommand(
            client_user_id=str(UUID(int=1)), amount_minor=amount, idempotency_key=key
        )
    )
    return ticket.order_id, ticket.code


class TestWithdrawal:
    def test_initiate_reserves_funds_and_issues_code(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, n=1, msisdn=CLIENT_MSISDN, balance=100_000)
        order_id, code = _initiate(services, 30_000)

        wallet = uow.wallets.get_for_user(EntityId(str(UUID(int=1))), XOF)
        assert wallet is not None
        assert wallet.reserved == Money(30_000, XOF)  # frais 0 pour le retrait
        assert wallet.available == Money(70_000, XOF)
        order = uow.cash_orders.get(EntityId(order_id))
        assert order is not None and order.status is CashOrderStatus.INITIATED
        assert len(code) == 8

    def test_initiate_insufficient_funds_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, n=1, msisdn=CLIENT_MSISDN, balance=1_000)
        with pytest.raises(InsufficientFunds):
            _initiate(services, 5_000)

    def test_confirm_by_agent_settles_and_grows_float(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _enroll_agent(services, uow, float_cap=1_000_000, initial=0)
        _user(uow, n=1, msisdn=CLIENT_MSISDN, balance=100_000)
        order_id, code = _initiate(services, 30_000)

        result = ConfirmCashWithdrawal(services=services, codes=CODES).execute(
            ConfirmWithdrawalCommand(agent_user_id=str(UUID(int=9)), code=code)
        )
        assert result.amount_minor == 30_000
        assert result.commission_minor == 300  # 1 %

        wallet = uow.wallets.get_for_user(EntityId(str(UUID(int=1))), XOF)
        assert wallet is not None
        assert wallet.reserved == Money(0, XOF)
        assert wallet.available == Money(70_000, XOF)
        assert wallet.balance == Money(70_000, XOF)  # les fonds ont quitté le wallet

        agent = uow.agents.get_by_user_id(EntityId(str(UUID(int=9))))
        assert agent is not None
        assert agent.float_available == Money(30_300, XOF)  # amount + commission

        order = uow.cash_orders.get(EntityId(order_id))
        assert order is not None and order.status is CashOrderStatus.CONFIRMED
        [txn] = uow.ledger.get_by_reference(f"WDL-{order_id}")
        assert txn.is_balanced

    def test_confirm_wrong_code_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _enroll_agent(services, uow, float_cap=1_000_000, initial=0)
        _user(uow, n=1, msisdn=CLIENT_MSISDN, balance=100_000)
        _initiate(services, 30_000)
        with pytest.raises(WithdrawalCodeInvalid):
            ConfirmCashWithdrawal(services=services, codes=CODES).execute(
                ConfirmWithdrawalCommand(agent_user_id=str(UUID(int=9)), code="ZZZZZZZZ")
            )

    def test_confirm_expired_code_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork, clock: FixedClock
    ) -> None:
        _enroll_agent(services, uow, float_cap=1_000_000, initial=0)
        _user(uow, n=1, msisdn=CLIENT_MSISDN, balance=100_000)
        _order_id, code = _initiate(services, 30_000)
        clock.advance(minutes=20)  # TTL = 15 min
        with pytest.raises(WithdrawalCodeExpired):
            ConfirmCashWithdrawal(services=services, codes=CODES).execute(
                ConfirmWithdrawalCommand(agent_user_id=str(UUID(int=9)), code=code)
            )

    def test_cancel_releases_reservation(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, n=1, msisdn=CLIENT_MSISDN, balance=100_000)
        order_id, _code = _initiate(services, 30_000)
        CancelCashWithdrawal(services=services).execute(
            CancelWithdrawalCommand(client_user_id=str(UUID(int=1)), order_id=order_id)
        )
        wallet = uow.wallets.get_for_user(EntityId(str(UUID(int=1))), XOF)
        assert wallet is not None
        assert wallet.reserved == Money(0, XOF)
        assert wallet.available == Money(100_000, XOF)
        order = uow.cash_orders.get(EntityId(order_id))
        assert order is not None and order.status is CashOrderStatus.CANCELLED

    def test_confirmed_order_cannot_be_cancelled(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _enroll_agent(services, uow, float_cap=1_000_000, initial=0)
        _user(uow, n=1, msisdn=CLIENT_MSISDN, balance=100_000)
        order_id, code = _initiate(services, 30_000)
        ConfirmCashWithdrawal(services=services, codes=CODES).execute(
            ConfirmWithdrawalCommand(agent_user_id=str(UUID(int=9)), code=code)
        )
        with pytest.raises(InvalidAccountState):
            CancelCashWithdrawal(services=services).execute(
                CancelWithdrawalCommand(client_user_id=str(UUID(int=1)), order_id=order_id)
            )


class TestEnrollAgentEdges:
    def test_unknown_user_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput, match="introuvable"):
            EnrollAgent(services=services).execute(
                EnrollAgentCommand(user_id=str(UUID(int=404)), float_cap_minor=1_000)
            )

    def test_view_serialises(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        _user(uow, n=9, msisdn=AGENT_MSISDN)
        view = EnrollAgent(services=services).execute(
            EnrollAgentCommand(
                user_id=str(UUID(int=9)), float_cap_minor=200_000, commission_bps=100
            )
        )
        payload = view.to_dict()
        assert payload["float_cap_minor"] == 200_000
        assert payload["commission_bps"] == 100
        assert payload["status"] == "ACTIVE"


class TestCashDepositEdges:
    def test_non_positive_amount_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput, match="strictement positif"):
            _deposit_uc(services).execute(
                CreateCashDepositCommand(
                    agent_user_id=str(UUID(int=9)),
                    client_phone_number=CLIENT_MSISDN,
                    amount_minor=0,
                    idempotency_key="dep-key-neg1",
                )
            )

    def test_malformed_phone_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput):
            _deposit_uc(services).execute(
                CreateCashDepositCommand(
                    agent_user_id=str(UUID(int=9)),
                    client_phone_number="not-a-number",
                    amount_minor=1_000,
                    idempotency_key="dep-key-bad1",
                )
            )

    def test_unknown_client_rejected(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        _enroll_agent(services, uow, float_cap=1_000_000, initial=500_000)
        with pytest.raises(RecipientNotFound):
            _deposit_uc(services).execute(
                CreateCashDepositCommand(
                    agent_user_id=str(UUID(int=9)),
                    client_phone_number="+2250700000042",
                    amount_minor=1_000,
                    idempotency_key="dep-key-nocli",
                )
            )

    def test_zero_commission_deposit(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        _enroll_agent(services, uow, float_cap=1_000_000, initial=500_000, bps=0)
        _user(uow, n=1, msisdn=CLIENT_MSISDN)
        receipt = _deposit_uc(services).execute(
            CreateCashDepositCommand(
                agent_user_id=str(UUID(int=9)),
                client_phone_number=CLIENT_MSISDN,
                amount_minor=40_000,
                idempotency_key="dep-key-zero1",
            )
        )
        assert receipt.commission_minor == 0
        agent = uow.agents.get_by_user_id(EntityId(str(UUID(int=9))))
        assert agent is not None
        assert agent.float_available == Money(460_000, XOF)  # 500k - 40k, pas de commission

    def test_replay_returns_same_receipt(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _enroll_agent(services, uow, float_cap=1_000_000, initial=500_000)
        _user(uow, n=1, msisdn=CLIENT_MSISDN)
        cmd = CreateCashDepositCommand(
            agent_user_id=str(UUID(int=9)),
            client_phone_number=CLIENT_MSISDN,
            amount_minor=40_000,
            idempotency_key="dep-key-replay",
        )
        first = _deposit_uc(services).execute(cmd)
        second = _deposit_uc(services).execute(cmd)
        assert second == first


class TestWithdrawalEdges:
    def test_non_positive_amount_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput, match="strictement positif"):
            _initiate(services, 0, key="wdl-key-neg1")

    def test_short_idempotency_key_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, n=1, msisdn=CLIENT_MSISDN, balance=100_000)
        with pytest.raises(InvalidInput):
            _initiate(services, 10_000, key="x")

    def test_unknown_client_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput, match="introuvable"):
            _initiate(services, 10_000, key="wdl-key-nocli")

    def test_replay_returns_same_ticket(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, n=1, msisdn=CLIENT_MSISDN, balance=100_000)
        order_id, code = _initiate(services, 30_000, key="wdl-key-replay")
        again_id, again_code = _initiate(services, 30_000, key="wdl-key-replay")
        assert (again_id, again_code) == (order_id, code)

    def test_confirm_empty_code_rejected(self, services: AppServices) -> None:
        with pytest.raises(WithdrawalCodeInvalid):
            ConfirmCashWithdrawal(services=services, codes=CODES).execute(
                ConfirmWithdrawalCommand(agent_user_id=str(UUID(int=9)), code="   ")
            )

    def test_confirm_zero_commission_serialises(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _enroll_agent(services, uow, float_cap=1_000_000, initial=0, bps=0)
        _user(uow, n=1, msisdn=CLIENT_MSISDN, balance=100_000)
        _order_id, code = _initiate(services, 30_000)
        result = ConfirmCashWithdrawal(services=services, codes=CODES).execute(
            ConfirmWithdrawalCommand(agent_user_id=str(UUID(int=9)), code=code)
        )
        assert result.commission_minor == 0
        assert result.to_dict()["amount_minor"] == 30_000
        agent = uow.agents.get_by_user_id(EntityId(str(UUID(int=9))))
        assert agent is not None
        assert agent.float_available == Money(30_000, XOF)

    def test_cancel_unknown_order_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput, match="introuvable"):
            CancelCashWithdrawal(services=services).execute(
                CancelWithdrawalCommand(
                    client_user_id=str(UUID(int=1)), order_id=str(UUID(int=999))
                )
            )
