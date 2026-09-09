"""Tests de l'agrégat ``SavingsPlan`` (BE-050) : versements, échéancier, intérêts."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from flash.domain.savings.plan import SavingsFrequency, SavingsPlan, SavingsPlanStatus
from flash.domain.shared.errors import InvalidAccountState, InvalidInput
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import XOF, Currency, Money

T0 = datetime(2026, 1, 1, tzinfo=UTC)
PLAN = EntityId(UUID(int=1))
WALLET = EntityId(UUID(int=2))
USER = EntityId(UUID(int=3))


def xof(n: int) -> Money:
    return Money(n, XOF)


def new_plan(**kw: object) -> SavingsPlan:
    params: dict[str, object] = {
        "plan_id": PLAN,
        "wallet_id": WALLET,
        "user_id": USER,
        "currency": XOF,
        "name": "Voyage",
        "now": T0,
    }
    params.update(kw)
    return SavingsPlan.open(**params)  # type: ignore[arg-type]


class TestOpen:
    def test_open_plain_plan(self) -> None:
        plan = new_plan()
        assert plan.balance == xof(0)
        assert plan.is_active
        assert plan.frequency is SavingsFrequency.NONE
        assert plan.next_contribution_at is None
        assert [e.name for e in plan.pull_events()] == ["SavingsPlanOpened"]

    def test_open_scheduled_plan_sets_next_contribution(self) -> None:
        plan = new_plan(
            frequency=SavingsFrequency.WEEKLY, contribution_minor=5_000, annual_rate_bps=350
        )
        assert plan.next_contribution_at == T0 + timedelta(days=7)
        assert plan.contribution == xof(5_000)

    def test_scheduled_without_contribution_rejected(self) -> None:
        with pytest.raises(InvalidInput, match="versement"):
            new_plan(frequency=SavingsFrequency.MONTHLY, contribution_minor=0)

    def test_blank_name_rejected(self) -> None:
        with pytest.raises(InvalidInput, match="nom du plan"):
            new_plan(name="   ")

    def test_rate_out_of_bounds_rejected(self) -> None:
        with pytest.raises(InvalidInput, match=r"[Tt]aux"):
            new_plan(annual_rate_bps=2_500)

    def test_non_positive_target_rejected(self) -> None:
        with pytest.raises(InvalidInput, match="objectif"):
            new_plan(target_minor=0)

    def test_reconstruction_rejects_wrong_currency(self) -> None:
        with pytest.raises(InvalidInput, match="devise"):
            SavingsPlan(
                id=PLAN,
                wallet_id=WALLET,
                user_id=USER,
                currency=XOF,
                name="X",
                balance=Money(0, Currency.of("EUR")),
                annual_rate_bps=0,
                frequency=SavingsFrequency.NONE,
                contribution=xof(0),
                created_at=T0,
            )

    def test_reconstruction_rejects_negative_amount(self) -> None:
        with pytest.raises(InvalidInput, match="négatif"):
            SavingsPlan(
                id=PLAN,
                wallet_id=WALLET,
                user_id=USER,
                currency=XOF,
                name="X",
                balance=xof(0),
                annual_rate_bps=0,
                frequency=SavingsFrequency.NONE,
                contribution=xof(-1),
                created_at=T0,
            )


class TestMoves:
    def test_deposit_and_partial_withdraw(self) -> None:
        plan = new_plan()
        plan.pull_events()
        plan.deposit(xof(30_000), T0)
        assert plan.balance == xof(30_000)
        assert [e.name for e in plan.pull_events()] == ["SavingsPlanFunded"]
        plan.withdraw(xof(10_000), T0)
        assert plan.balance == xof(20_000)
        assert [e.name for e in plan.pull_events()] == ["SavingsPlanWithdrawn"]

    def test_withdraw_more_than_balance_rejected(self) -> None:
        plan = new_plan()
        plan.deposit(xof(1_000), T0)
        with pytest.raises(InvalidInput, match="insuffisant"):
            plan.withdraw(xof(1_001), T0)

    @pytest.mark.parametrize("bad", [0, -5])
    def test_non_positive_amount_rejected(self, bad: int) -> None:
        plan = new_plan()
        with pytest.raises(InvalidInput, match="strictement positif"):
            plan.deposit(xof(bad), T0)

    def test_wrong_currency_rejected(self) -> None:
        plan = new_plan()
        with pytest.raises(InvalidInput, match=r"[Dd]evise"):
            plan.deposit(Money(10, Currency.of("EUR")), T0)

    def test_close_returns_balance_and_locks_plan(self) -> None:
        plan = new_plan()
        plan.deposit(xof(12_000), T0)
        plan.pull_events()
        returned = plan.close(T0)
        assert returned == xof(12_000)
        assert plan.balance == xof(0)
        assert plan.status is SavingsPlanStatus.CLOSED
        assert [e.name for e in plan.pull_events()] == ["SavingsPlanClosed"]

    def test_operations_on_closed_plan_rejected(self) -> None:
        plan = new_plan()
        plan.close(T0)
        for action in (
            lambda: plan.deposit(xof(1), T0),
            lambda: plan.withdraw(xof(1), T0),
            lambda: plan.close(T0),
        ):
            with pytest.raises(InvalidAccountState):
                action()


class TestSchedule:
    def test_contribution_due_and_advance(self) -> None:
        plan = new_plan(frequency=SavingsFrequency.WEEKLY, contribution_minor=5_000)
        assert plan.contribution_due(T0) is False
        assert plan.contribution_due(T0 + timedelta(days=8)) is True
        plan.advance_schedule(T0 + timedelta(days=8))
        assert plan.next_contribution_at == T0 + timedelta(days=14)

    def test_advance_catches_up_multiple_missed_cycles(self) -> None:
        plan = new_plan(frequency=SavingsFrequency.WEEKLY, contribution_minor=5_000)
        plan.advance_schedule(T0 + timedelta(days=30))
        assert plan.next_contribution_at == T0 + timedelta(days=35)

    def test_advance_noop_when_not_scheduled(self) -> None:
        plan = new_plan()
        plan.advance_schedule(T0 + timedelta(days=90))
        assert plan.next_contribution_at is None

    def test_skip_contribution_emits_event_and_advances(self) -> None:
        plan = new_plan(frequency=SavingsFrequency.MONTHLY, contribution_minor=5_000)
        plan.pull_events()
        plan.skip_contribution(T0 + timedelta(days=31))
        assert [e.name for e in plan.pull_events()] == ["SavingsContributionSkipped"]
        assert plan.next_contribution_at == T0 + timedelta(days=60)


class TestInterest:
    def test_accrue_then_capitalise(self) -> None:
        # 1 000 000 XOF à 3,65 %/an => 100 XOF/jour ; sur 10 jours => 1 000 XOF.
        plan = new_plan(annual_rate_bps=365)
        plan.deposit(xof(1_000_000), T0)
        plan.pull_events()

        plan.accrue(T0 + timedelta(days=10))
        assert plan.accrued_interest_minor == 1_000
        assert [e.name for e in plan.pull_events()] == ["SavingsInterestAccrued"]

        capitalised = plan.capitalise(T0 + timedelta(days=10))
        assert capitalised == xof(1_000)
        assert plan.balance == xof(1_001_000)
        assert plan.accrued_interest_minor == 0
        assert [e.name for e in plan.pull_events()] == ["SavingsInterestCapitalised"]

    def test_accrue_keeps_sub_unit_remainder(self) -> None:
        plan = new_plan(annual_rate_bps=365)
        plan.deposit(xof(100), T0)  # 0,01 XOF/jour
        plan.accrue(T0 + timedelta(days=10))  # 0,1 XOF accumulés
        assert plan.capitalise(T0 + timedelta(days=10)) == xof(0)
        assert plan.accrued_micro > 0

    def test_accrue_noop_without_rate_or_balance(self) -> None:
        plan = new_plan(annual_rate_bps=0)
        plan.deposit(xof(1_000_000), T0)
        assert plan.accrue(T0 + timedelta(days=10)) == 0
        assert plan.accrued_interest_minor == 0

        earning = new_plan(annual_rate_bps=365)
        assert earning.accrue(T0 + timedelta(days=10)) == 0  # solde nul

    def test_accrue_noop_when_time_did_not_advance(self) -> None:
        plan = new_plan(annual_rate_bps=365)
        plan.deposit(xof(1_000_000), T0)
        assert plan.accrue(T0) == 0

    def test_accrue_below_one_micro_records_nothing(self) -> None:
        plan = new_plan(annual_rate_bps=1)
        plan.deposit(xof(1), T0)
        assert plan.accrue(T0 + timedelta(seconds=1)) == 0  # arrondi à 0 micro
        assert plan.pull_events()[-1].name == "SavingsPlanFunded"
        assert plan.last_accrual_at == T0 + timedelta(seconds=1)

    def test_capitalise_noop_when_nothing_accrued(self) -> None:
        plan = new_plan(annual_rate_bps=365)
        plan.deposit(xof(1_000_000), T0)
        assert plan.capitalise(T0) == xof(0)
        assert plan.pull_events()[-1].name == "SavingsPlanFunded"

    def test_accrue_and_capitalise_rejected_on_closed_plan(self) -> None:
        plan = new_plan(annual_rate_bps=365)
        plan.close(T0)
        with pytest.raises(InvalidAccountState):
            plan.accrue(T0 + timedelta(days=1))
        with pytest.raises(InvalidAccountState):
            plan.capitalise(T0 + timedelta(days=1))


class TestReadModel:
    def test_progress_bps(self) -> None:
        plan = new_plan(target_minor=100_000)
        plan.deposit(xof(25_000), T0)
        assert plan.progress_bps == 2_500
        plan.deposit(xof(200_000), T0)
        assert plan.progress_bps == 10_000  # plafonné
        assert new_plan().progress_bps is None

    def test_repr(self) -> None:
        plan = new_plan(annual_rate_bps=350)
        plan.deposit(xof(4_200), T0)
        assert "4200" in repr(plan) and "350bps" in repr(plan)
