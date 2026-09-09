"""Tests des cas d'usage épargne synchrones (BE-050 / BE-051 / BE-054)."""

from __future__ import annotations

from uuid import UUID

import pytest

from flash.application.savings.operations import (
    CloseSavingsPlan,
    CloseSavingsPlanCommand,
    ContributeToSavings,
    ContributeToSavingsCommand,
    ListSavingsPlans,
    ListSavingsPlansCommand,
    OpenSavingsPlan,
    OpenSavingsPlanCommand,
    WithdrawFromSavings,
    WithdrawFromSavingsCommand,
)
from flash.application.services import AppServices
from flash.application.statement.queries import ListStatement, ListStatementCommand
from flash.domain.identity.pin import Pin
from flash.domain.identity.user import User
from flash.domain.ledger.transaction import TransactionKind, sum_postings
from flash.domain.shared.errors import InsufficientFunds, InvalidAccountState, InvalidInput
from flash.domain.shared.identifiers import CountryCode, EntityId, Msisdn
from flash.domain.shared.money import XOF, Money
from flash.domain.wallet.wallet import Wallet
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


def _open(services: AppServices, **kw: object) -> str:
    view = OpenSavingsPlan(services=services).execute(
        OpenSavingsPlanCommand(user_id=USER_ID, name="Voyage", **kw)  # type: ignore[arg-type]
    )
    return view.plan_id


class TestOpenPlan:
    def test_open_plain_plan_and_list(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        plan_id = _open(services, target_minor=1_000_000, annual_rate_bps=350)
        plans = ListSavingsPlans(services=services).execute(
            ListSavingsPlansCommand(user_id=USER_ID)
        )
        assert [p.plan_id for p in plans] == [plan_id]
        assert plans[0].annual_rate_bps == 350
        assert plans[0].to_dict()["target_minor"] == 1_000_000

    def test_open_scheduled_plan(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        _user(uow)
        _open(services, frequency="WEEKLY", contribution_minor=5_000)
        plans = ListSavingsPlans(services=services).execute(
            ListSavingsPlansCommand(user_id=USER_ID)
        )
        assert plans[0].frequency == "WEEKLY"
        assert plans[0].next_contribution_at is not None

    def test_unknown_frequency_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        with pytest.raises(InvalidInput, match=r"[Ff]réquence"):
            OpenSavingsPlan(services=services).execute(
                OpenSavingsPlanCommand(user_id=USER_ID, name="X", frequency="DAILY")
            )

    def test_blank_name_rejected(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        _user(uow)
        with pytest.raises(InvalidInput, match="nom du plan"):
            OpenSavingsPlan(services=services).execute(
                OpenSavingsPlanCommand(user_id=USER_ID, name="  ")
            )

    def test_bad_target_date_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        with pytest.raises(InvalidInput, match="ISO 8601"):
            OpenSavingsPlan(services=services).execute(
                OpenSavingsPlanCommand(user_id=USER_ID, name="X", target_date="bientôt")
            )

    def test_naive_target_date_is_accepted(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        view = OpenSavingsPlan(services=services).execute(
            OpenSavingsPlanCommand(user_id=USER_ID, name="X", target_date="2027-06-01T00:00:00")
        )
        assert view.target_date is not None and view.target_date.endswith("+00:00")


class TestContributeWithdraw:
    def test_contribute_moves_available_into_plan(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=100_000)
        plan_id = _open(services)
        receipt = ContributeToSavings(services=services).execute(
            ContributeToSavingsCommand(
                user_id=USER_ID, plan_id=plan_id, amount_minor=30_000, idempotency_key="sav-in-0001"
            )
        )
        assert receipt.direction == "in"
        assert receipt.wallet_available_after_minor == 70_000
        assert receipt.plan_balance_after_minor == 30_000
        assert receipt.saved_after_minor == 30_000

        wallet = uow.wallets.get_for_user(EntityId(USER_ID), XOF)
        assert wallet is not None
        assert wallet.available == Money(70_000, XOF)
        assert wallet.saved == Money(30_000, XOF)
        assert wallet.balance == Money(100_000, XOF)

        [txn] = uow.ledger.transactions
        assert txn.kind is TransactionKind.SAVINGS_DEPOSIT
        assert txn.is_balanced and sum_postings(txn.postings) == {"XOF": 0}

    def test_contribute_insufficient_funds_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=1_000)
        plan_id = _open(services)
        with pytest.raises(InsufficientFunds):
            ContributeToSavings(services=services).execute(
                ContributeToSavingsCommand(
                    user_id=USER_ID,
                    plan_id=plan_id,
                    amount_minor=5_000,
                    idempotency_key="sav-broke",
                )
            )

    def test_contribute_is_idempotent(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=100_000)
        plan_id = _open(services)
        cmd = ContributeToSavingsCommand(
            user_id=USER_ID, plan_id=plan_id, amount_minor=30_000, idempotency_key="sav-in-rep"
        )
        first = ContributeToSavings(services=services).execute(cmd)
        second = ContributeToSavings(services=services).execute(cmd)
        assert first == second
        wallet = uow.wallets.get_for_user(EntityId(USER_ID), XOF)
        assert wallet is not None and wallet.available == Money(70_000, XOF)

    def test_contribute_bad_idempotency_key_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=100_000)
        plan_id = _open(services)
        with pytest.raises(InvalidInput):
            ContributeToSavings(services=services).execute(
                ContributeToSavingsCommand(
                    user_id=USER_ID, plan_id=plan_id, amount_minor=1_000, idempotency_key="x"
                )
            )

    def test_contribute_non_positive_amount_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=100_000)
        plan_id = _open(services)
        with pytest.raises(InvalidInput, match="strictement positif"):
            ContributeToSavings(services=services).execute(
                ContributeToSavingsCommand(
                    user_id=USER_ID, plan_id=plan_id, amount_minor=0, idempotency_key="sav-zero"
                )
            )

    def test_contribute_unknown_plan_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=100_000)
        with pytest.raises(InvalidInput, match="introuvable"):
            ContributeToSavings(services=services).execute(
                ContributeToSavingsCommand(
                    user_id=USER_ID,
                    plan_id=str(UUID(int=999)),
                    amount_minor=1_000,
                    idempotency_key="sav-noplan",
                )
            )

    def test_contribute_malformed_plan_id_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=100_000)
        with pytest.raises(InvalidInput, match="introuvable"):
            ContributeToSavings(services=services).execute(
                ContributeToSavingsCommand(
                    user_id=USER_ID,
                    plan_id="not-a-uuid",
                    amount_minor=1_000,
                    idempotency_key="sav-badid",
                )
            )

    def test_contribute_to_other_users_plan_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=100_000)
        plan_id = _open(services)

        other = User.register(
            user_id=EntityId(str(UUID(int=42))),
            country=CI,
            msisdn=Msisdn("+2250700000042"),
            pin_hash=FakePinHasher().hash(Pin("1397")),
            now=FixedClock().now(),
        )
        other.activate(FixedClock().now())
        other.pull_events()
        uow.users.add(other)
        other_wallet = Wallet.open(
            wallet_id=EntityId(str(UUID(int=542))),
            user_id=other.id,
            currency=XOF,
            now=FixedClock().now(),
        )
        other_wallet.credit(Money(100_000, XOF), FixedClock().now())
        other_wallet.pull_events()
        uow.wallets.add(other_wallet)

        with pytest.raises(InvalidInput, match="introuvable"):
            ContributeToSavings(services=services).execute(
                ContributeToSavingsCommand(
                    user_id=str(UUID(int=42)),
                    plan_id=plan_id,
                    amount_minor=1_000,
                    idempotency_key="sav-otheruser",
                )
            )

    def test_partial_withdraw_returns_to_available(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=100_000)
        plan_id = _open(services)
        ContributeToSavings(services=services).execute(
            ContributeToSavingsCommand(
                user_id=USER_ID, plan_id=plan_id, amount_minor=40_000, idempotency_key="sav-in-a"
            )
        )
        receipt = WithdrawFromSavings(services=services).execute(
            WithdrawFromSavingsCommand(
                user_id=USER_ID, plan_id=plan_id, amount_minor=15_000, idempotency_key="sav-out-a"
            )
        )
        assert receipt.direction == "out"
        assert receipt.wallet_available_after_minor == 75_000
        assert receipt.plan_balance_after_minor == 25_000
        for txn in uow.ledger.transactions:
            assert txn.is_balanced

    def test_withdraw_more_than_plan_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=100_000)
        plan_id = _open(services)
        ContributeToSavings(services=services).execute(
            ContributeToSavingsCommand(
                user_id=USER_ID, plan_id=plan_id, amount_minor=5_000, idempotency_key="sav-in-s"
            )
        )
        with pytest.raises(InvalidInput, match="insuffisant"):
            WithdrawFromSavings(services=services).execute(
                WithdrawFromSavingsCommand(
                    user_id=USER_ID,
                    plan_id=plan_id,
                    amount_minor=6_000,
                    idempotency_key="sav-out-s",
                )
            )

    def test_savings_moves_appear_in_statement(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=100_000)
        plan_id = _open(services)
        ContributeToSavings(services=services).execute(
            ContributeToSavingsCommand(
                user_id=USER_ID, plan_id=plan_id, amount_minor=40_000, idempotency_key="sav-in-st"
            )
        )
        WithdrawFromSavings(services=services).execute(
            WithdrawFromSavingsCommand(
                user_id=USER_ID, plan_id=plan_id, amount_minor=15_000, idempotency_key="sav-out-st"
            )
        )
        page = ListStatement(services=services).execute(ListStatementCommand(user_id=USER_ID))
        moves = [ln for ln in page.lines if ln.kind.startswith("SAVINGS")]
        assert {(m.direction, m.amount_minor) for m in moves} == {("out", 40_000), ("in", 15_000)}
        assert all(m.counterparty_masked == "Voyage" and m.fee_minor == 0 for m in moves)


class TestClose:
    def test_close_repatriates_everything(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=100_000)
        plan_id = _open(services)
        ContributeToSavings(services=services).execute(
            ContributeToSavingsCommand(
                user_id=USER_ID, plan_id=plan_id, amount_minor=40_000, idempotency_key="sav-in-cl"
            )
        )
        result = CloseSavingsPlan(services=services).execute(
            CloseSavingsPlanCommand(user_id=USER_ID, plan_id=plan_id)
        )
        assert result.returned_minor == 40_000
        assert result.wallet_available_after_minor == 100_000

        wallet = uow.wallets.get_for_user(EntityId(USER_ID), XOF)
        assert wallet is not None
        assert wallet.saved == Money(0, XOF) and wallet.balance == Money(100_000, XOF)
        plans = ListSavingsPlans(services=services).execute(
            ListSavingsPlansCommand(user_id=USER_ID)
        )
        assert plans[0].status == "CLOSED"

    def test_close_empty_plan_moves_no_money(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=100_000)
        plan_id = _open(services)
        result = CloseSavingsPlan(services=services).execute(
            CloseSavingsPlanCommand(user_id=USER_ID, plan_id=plan_id)
        )
        assert result.returned_minor == 0
        assert uow.ledger.transactions == []

    def test_close_twice_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=100_000)
        plan_id = _open(services)
        CloseSavingsPlan(services=services).execute(
            CloseSavingsPlanCommand(user_id=USER_ID, plan_id=plan_id)
        )
        with pytest.raises(InvalidAccountState):
            CloseSavingsPlan(services=services).execute(
                CloseSavingsPlanCommand(user_id=USER_ID, plan_id=plan_id)
            )
