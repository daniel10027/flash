"""Tests des cas d'usage interop opérateurs : initiation payout / collect (BE-065/066)."""

from __future__ import annotations

from uuid import UUID

import pytest

from flash.application.operators.callbacks import (
    HandleOperatorCallback,
    OperatorCallbackCommand,
)
from flash.application.operators.operations import (
    ListOperatorTransfers,
    ListOperatorTransfersCommand,
    SendToOperatorAccount,
    SendToOperatorAccountCommand,
    TopUpFromOperator,
    TopUpFromOperatorCommand,
)
from flash.application.services import AppServices
from flash.domain.identity.pin import Pin
from flash.domain.identity.user import User
from flash.domain.ledger.transaction import sum_postings
from flash.domain.limits.limits import KycPolicy, LimitPolicy
from flash.domain.pricing.pricing import PricingService
from flash.domain.shared.errors import (
    InsufficientFunds,
    InvalidInput,
    OperatorGatewayRejected,
)
from flash.domain.shared.identifiers import CountryCode, EntityId, Msisdn
from flash.domain.shared.money import XOF, Money
from flash.domain.wallet.wallet import Wallet
from flash.infrastructure.limits import NullLimitCounter, build_limit_repository
from flash.infrastructure.operator_gateway import SandboxOperatorGateway
from flash.infrastructure.pricing import build_pricing_repository
from flash.infrastructure.reference import StaticReferenceDirectory
from tests.support.fakes import (
    FakePinHasher,
    FixedClock,
    InMemoryIdempotencyStore,
    RecordingEventPublisher,
    SeqIdGenerator,
)
from tests.support.repositories import InMemoryUnitOfWork

CI = CountryCode("CI")
USER_ID = str(UUID(int=1))
MSISDN = "+2250700000001"
TARGET = "+2250712345678"


class _RejectingGateway:
    def payout(self, **_: object) -> object:
        from flash.application.operators.ports import GatewayAck

        return GatewayAck(accepted=False, external_ref="", reason="OPERATOR_DOWN")

    def collect(self, **_: object) -> object:
        from flash.application.operators.ports import GatewayAck

        return GatewayAck(accepted=False, external_ref="", reason="OPERATOR_DOWN")


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def events() -> RecordingEventPublisher:
    return RecordingEventPublisher()


@pytest.fixture
def services(
    uow: InMemoryUnitOfWork, clock: FixedClock, events: RecordingEventPublisher
) -> AppServices:
    return AppServices(
        uow=lambda: uow,
        clock=clock,
        ids=SeqIdGenerator(),
        events=events,
        idempotency=InMemoryIdempotencyStore(),
    )


def _user(uow: InMemoryUnitOfWork, *, balance: int = 0) -> None:
    user = User.register(
        user_id=EntityId(USER_ID),
        country=CI,
        msisdn=Msisdn(MSISDN),
        pin_hash=FakePinHasher().hash(Pin("1397")),
        now=FixedClock().now(),
    )
    user.activate(FixedClock().now())
    user.pull_events()
    uow.users.add(user)
    wallet = Wallet.open(
        wallet_id=EntityId(str(UUID(int=500))),
        user_id=user.id,
        currency=XOF,
        now=FixedClock().now(),
    )
    if balance:
        wallet.credit(Money(balance, XOF), FixedClock().now())
    wallet.pull_events()
    uow.wallets.add(wallet)


def _pricing() -> PricingService:
    return PricingService(build_pricing_repository())


def _limits() -> LimitPolicy:
    return LimitPolicy(build_limit_repository(), NullLimitCounter())


def _payout_uc(services: AppServices, *, gateway: object | None = None) -> SendToOperatorAccount:
    return SendToOperatorAccount(
        services=services,
        gateway=gateway or SandboxOperatorGateway(pepper="t"),  # type: ignore[arg-type]
        reference=StaticReferenceDirectory(),
        pricing=_pricing(),
        limits=_limits(),
        kyc=KycPolicy(),
    )


def _topup_uc(services: AppServices, *, gateway: object | None = None) -> TopUpFromOperator:
    return TopUpFromOperator(
        services=services,
        gateway=gateway or SandboxOperatorGateway(pepper="t"),  # type: ignore[arg-type]
        reference=StaticReferenceDirectory(),
        pricing=_pricing(),
        limits=_limits(),
        kyc=KycPolicy(),
    )


class TestPayout:
    def test_reserves_funds_and_calls_gateway(
        self, services: AppServices, uow: InMemoryUnitOfWork, events: RecordingEventPublisher
    ) -> None:
        _user(uow, balance=100_000)
        receipt = _payout_uc(services).execute(
            SendToOperatorAccountCommand(
                user_id=USER_ID,
                operator="ORANGE_CI",
                msisdn=TARGET,
                amount_minor=50_000,
                idempotency_key="opo-key-0001",
            )
        )
        assert receipt.status == "PENDING" and receipt.direction == "PAYOUT"
        assert receipt.fee_minor == 750  # 1,5 %
        assert receipt.external_ref and receipt.external_ref.startswith("op_")
        assert receipt.wallet_available_after_minor == 100_000 - 50_750

        wallet = uow.wallets.get_for_user(EntityId(USER_ID), XOF)
        assert wallet is not None
        assert wallet.available == Money(49_250, XOF)
        assert wallet.reserved == Money(50_750, XOF)
        assert uow.ledger.transactions == []  # rien tant que non confirmé
        assert "OperatorTransferInitiated" in events.names()

    def test_insufficient_funds_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=1_000)
        with pytest.raises(InsufficientFunds):
            _payout_uc(services).execute(
                SendToOperatorAccountCommand(
                    user_id=USER_ID,
                    operator="ORANGE_CI",
                    msisdn=TARGET,
                    amount_minor=50_000,
                    idempotency_key="opo-key-broke",
                )
            )

    def test_unknown_operator_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=100_000)
        with pytest.raises(InvalidInput, match="Opérateur inconnu"):
            _payout_uc(services).execute(
                SendToOperatorAccountCommand(
                    user_id=USER_ID,
                    operator="NOPE_CI",
                    msisdn=TARGET,
                    amount_minor=1_000,
                    idempotency_key="opo-key-noop",
                )
            )

    def test_gateway_rejection_rolls_back_reservation(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=100_000)
        with pytest.raises(OperatorGatewayRejected):
            _payout_uc(services, gateway=_RejectingGateway()).execute(
                SendToOperatorAccountCommand(
                    user_id=USER_ID,
                    operator="ORANGE_CI",
                    msisdn=TARGET,
                    amount_minor=50_000,
                    idempotency_key="opo-key-reject",
                )
            )
        wallet = uow.wallets.get_for_user(EntityId(USER_ID), XOF)
        assert wallet is not None and wallet.reserved == Money(0, XOF)
        assert uow.operator_transfers.list_for_user(EntityId(USER_ID)) == []

    def test_is_idempotent(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        _user(uow, balance=100_000)
        cmd = SendToOperatorAccountCommand(
            user_id=USER_ID,
            operator="ORANGE_CI",
            msisdn=TARGET,
            amount_minor=50_000,
            idempotency_key="opo-key-rep",
        )
        first = _payout_uc(services).execute(cmd)
        second = _payout_uc(services).execute(cmd)
        assert first == second
        wallet = uow.wallets.get_for_user(EntityId(USER_ID), XOF)
        assert wallet is not None and wallet.reserved == Money(50_750, XOF)

    def test_bad_msisdn_rejected(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        _user(uow, balance=100_000)
        with pytest.raises(InvalidInput):
            _payout_uc(services).execute(
                SendToOperatorAccountCommand(
                    user_id=USER_ID,
                    operator="ORANGE_CI",
                    msisdn="pas-un-numero",
                    amount_minor=1_000,
                    idempotency_key="opo-key-badnum",
                )
            )

    def test_non_positive_amount_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=100_000)
        with pytest.raises(InvalidInput, match="strictement positif"):
            _payout_uc(services).execute(
                SendToOperatorAccountCommand(
                    user_id=USER_ID,
                    operator="ORANGE_CI",
                    msisdn=TARGET,
                    amount_minor=0,
                    idempotency_key="opo-key-zero",
                )
            )


class TestTopUp:
    def test_creates_pending_without_touching_wallet(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=1_000)
        receipt = _topup_uc(services).execute(
            TopUpFromOperatorCommand(
                user_id=USER_ID,
                operator="MTN_CI",
                msisdn=TARGET,
                amount_minor=30_000,
                idempotency_key="opc-key-0001",
            )
        )
        assert receipt.status == "PENDING" and receipt.direction == "COLLECT"
        assert receipt.fee_minor == 300  # 1 %
        wallet = uow.wallets.get_for_user(EntityId(USER_ID), XOF)
        assert wallet is not None and wallet.available == Money(1_000, XOF)
        assert uow.ledger.transactions == []

    def test_non_positive_amount_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=1_000)
        with pytest.raises(InvalidInput, match="strictement positif"):
            _topup_uc(services).execute(
                TopUpFromOperatorCommand(
                    user_id=USER_ID,
                    operator="MTN_CI",
                    msisdn=TARGET,
                    amount_minor=0,
                    idempotency_key="opc-key-zero",
                )
            )

    def test_bad_msisdn_rejected(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        _user(uow, balance=1_000)
        with pytest.raises(InvalidInput):
            _topup_uc(services).execute(
                TopUpFromOperatorCommand(
                    user_id=USER_ID,
                    operator="MTN_CI",
                    msisdn="x",
                    amount_minor=1_000,
                    idempotency_key="opc-key-badnum",
                )
            )

    def test_gateway_rejection_creates_no_transfer(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=1_000)
        with pytest.raises(OperatorGatewayRejected):
            _topup_uc(services, gateway=_RejectingGateway()).execute(
                TopUpFromOperatorCommand(
                    user_id=USER_ID,
                    operator="MTN_CI",
                    msisdn=TARGET,
                    amount_minor=30_000,
                    idempotency_key="opc-key-reject",
                )
            )
        assert uow.operator_transfers.list_for_user(EntityId(USER_ID)) == []


def test_list_transfers(services: AppServices, uow: InMemoryUnitOfWork) -> None:
    _user(uow, balance=200_000)
    _payout_uc(services).execute(
        SendToOperatorAccountCommand(
            user_id=USER_ID,
            operator="ORANGE_CI",
            msisdn=TARGET,
            amount_minor=50_000,
            idempotency_key="opo-list-1",
        )
    )
    _topup_uc(services).execute(
        TopUpFromOperatorCommand(
            user_id=USER_ID,
            operator="MTN_CI",
            msisdn=TARGET,
            amount_minor=10_000,
            idempotency_key="opc-list-1",
        )
    )
    lines = ListOperatorTransfers(services=services).execute(
        ListOperatorTransfersCommand(user_id=USER_ID)
    )
    assert {ln.direction for ln in lines} == {"PAYOUT", "COLLECT"}
    assert all(ln.status == "PENDING" for ln in lines)
    assert lines[0].to_dict()["status"] == "PENDING"


def test_payout_confirmed_then_settled_via_callback(
    services: AppServices, uow: InMemoryUnitOfWork
) -> None:
    _user(uow, balance=100_000)
    receipt = _payout_uc(services).execute(
        SendToOperatorAccountCommand(
            user_id=USER_ID,
            operator="ORANGE_CI",
            msisdn=TARGET,
            amount_minor=50_000,
            idempotency_key="opo-cb-1",
        )
    )
    HandleOperatorCallback(services=services).execute(
        OperatorCallbackCommand(
            operator="ORANGE_CI", reference=receipt.reference, status="SUCCEEDED"
        )
    )
    wallet = uow.wallets.get_for_user(EntityId(USER_ID), XOF)
    assert wallet is not None
    assert wallet.reserved == Money(0, XOF)
    assert wallet.balance == Money(49_250, XOF)  # a payé amount + fee
    [txn] = uow.ledger.transactions
    assert txn.is_balanced and sum_postings(txn.postings) == {"XOF": 0}
