"""Tests des jobs d'épargne : versements programmés (BE-052) et intérêts (BE-053)."""

from __future__ import annotations

from uuid import UUID

import pytest

from flash.application.jobs.savings import AccrueSavingsInterest, RunScheduledSavings
from flash.application.services import AppServices
from flash.application.statement.queries import ListStatement, ListStatementCommand
from flash.domain.savings.plan import SavingsFrequency, SavingsPlan
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import XOF, Money
from flash.domain.wallet.wallet import Wallet
from tests.support.fakes import (
    FixedClock,
    InMemoryIdempotencyStore,
    RecordingEventPublisher,
    SeqIdGenerator,
)
from tests.support.repositories import InMemoryUnitOfWork

USER = EntityId(str(UUID(int=1)))
WALLET = EntityId(str(UUID(int=500)))


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


def _wallet(uow: InMemoryUnitOfWork, *, available: int = 0, saved: int = 0) -> Wallet:
    wallet = Wallet.open(wallet_id=WALLET, user_id=USER, currency=XOF, now=FixedClock().now())
    if available or saved:
        wallet.credit(Money(available + saved, XOF), FixedClock().now())
    if saved:
        wallet.move_to_savings(Money(saved, XOF), FixedClock().now())
    wallet.pull_events()
    uow.wallets.add(wallet)
    return wallet


def _plan(
    uow: InMemoryUnitOfWork,
    *,
    n: int = 1,
    balance: int = 0,
    rate_bps: int = 0,
    frequency: SavingsFrequency = SavingsFrequency.NONE,
    contribution: int = 0,
) -> SavingsPlan:
    plan = SavingsPlan.open(
        plan_id=EntityId(str(UUID(int=700 + n))),
        wallet_id=WALLET,
        user_id=USER,
        currency=XOF,
        name=f"Plan {n}",
        now=FixedClock().now(),
        annual_rate_bps=rate_bps,
        frequency=frequency,
        contribution_minor=contribution,
    )
    if balance:
        plan.deposit(Money(balance, XOF), FixedClock().now())
    plan.pull_events()
    uow.savings.add(plan)
    return plan


class TestScheduledSavings:
    def test_due_contribution_is_funded_and_rescheduled(
        self, services: AppServices, uow: InMemoryUnitOfWork, clock: FixedClock
    ) -> None:
        _wallet(uow, available=100_000)
        _plan(uow, frequency=SavingsFrequency.WEEKLY, contribution=5_000)
        clock.advance(days=8)

        report = RunScheduledSavings(services=services).execute()
        assert (report.checked, report.funded, report.skipped) == (1, 1, 0)
        assert report.to_dict() == {"checked": 1, "funded": 1, "skipped": 0}

        plan = uow.savings.get(EntityId(str(UUID(int=701))))
        assert plan is not None and plan.balance == Money(5_000, XOF)
        wallet = uow.wallets.get(WALLET)
        assert wallet is not None
        assert wallet.saved == Money(5_000, XOF) and wallet.available == Money(95_000, XOF)
        [txn] = uow.ledger.transactions
        assert txn.is_balanced

        # Rejeu immédiat : plus rien d'échu.
        assert RunScheduledSavings(services=services).execute().checked == 0

    def test_insufficient_funds_skips_cleanly(
        self,
        services: AppServices,
        uow: InMemoryUnitOfWork,
        clock: FixedClock,
        events: RecordingEventPublisher,
    ) -> None:
        _wallet(uow, available=1_000)
        _plan(uow, frequency=SavingsFrequency.MONTHLY, contribution=5_000)
        clock.advance(days=31)

        report = RunScheduledSavings(services=services).execute()
        assert (report.checked, report.funded, report.skipped) == (1, 0, 1)
        assert "SavingsContributionSkipped" in events.names()
        assert uow.ledger.transactions == []

        plan = uow.savings.get(EntityId(str(UUID(int=701))))
        assert plan is not None and not plan.contribution_due(clock.now())

    def test_no_scheduled_plans_is_noop(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _wallet(uow, available=100_000)
        _plan(uow)  # frequency NONE
        report = RunScheduledSavings(services=services).execute()
        assert (report.checked, report.funded, report.skipped) == (0, 0, 0)


class TestInterestAccrual:
    def test_accrues_and_capitalises_whole_units(
        self, services: AppServices, uow: InMemoryUnitOfWork, clock: FixedClock
    ) -> None:
        _wallet(uow, available=0, saved=1_000_000)
        _plan(uow, balance=1_000_000, rate_bps=365)  # 100 XOF / jour
        clock.advance(days=10)

        report = AccrueSavingsInterest(services=services).execute()
        assert report.checked == 1
        assert report.capitalised_plans == 1
        assert report.capitalised_minor == 1_000

        plan = uow.savings.get(EntityId(str(UUID(int=701))))
        assert plan is not None and plan.balance == Money(1_001_000, XOF)
        wallet = uow.wallets.get(WALLET)
        assert wallet is not None and wallet.saved == Money(1_001_000, XOF)
        [txn] = uow.ledger.transactions
        assert txn.is_balanced
        assert report.to_dict()["capitalised_minor"] == 1_000

        page = ListStatement(services=services).execute(ListStatementCommand(user_id=str(USER)))
        [line] = page.lines
        assert line.kind == "INTEREST" and line.direction == "in"
        assert line.amount_minor == 1_000 and line.counterparty_masked == "Plan 1"

    def test_no_capitalisation_below_one_unit(
        self, services: AppServices, uow: InMemoryUnitOfWork, clock: FixedClock
    ) -> None:
        _wallet(uow, saved=100)
        _plan(uow, balance=100, rate_bps=365)  # 0,01 XOF / jour
        clock.advance(days=10)
        report = AccrueSavingsInterest(services=services).execute()
        assert report.capitalised_plans == 0 and report.capitalised_minor == 0
        assert uow.ledger.transactions == []
        plan = uow.savings.get(EntityId(str(UUID(int=701))))
        assert plan is not None and plan.accrued_micro > 0

    def test_paginates_across_pages(
        self,
        services: AppServices,
        uow: InMemoryUnitOfWork,
        clock: FixedClock,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        monkeypatch.setattr("flash.application.jobs.savings._PAGE", 1)
        _wallet(uow, saved=2_000_000)
        _plan(uow, n=1, balance=1_000_000, rate_bps=365)
        _plan(uow, n=2, balance=1_000_000, rate_bps=365)
        clock.advance(days=10)
        report = AccrueSavingsInterest(services=services).execute()
        assert report.checked == 2 and report.capitalised_plans == 2
