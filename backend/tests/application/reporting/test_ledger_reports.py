"""Tests des exports réglementaires & comptables (BE-077)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from flash.application.reporting.ledger_reports import (
    ExportMonthlyLedger,
    ExportMonthlyLedgerCommand,
    GetLedgerJournal,
    GetLedgerJournalCommand,
    GetTrialBalance,
    GetTrialBalanceCommand,
)
from flash.application.services import AppServices
from flash.domain.ledger.chart import AccountType
from flash.domain.ledger.transaction import LedgerTransaction
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import XOF, Money
from tests.support.fakes import (
    FixedClock,
    InMemoryIdempotencyStore,
    RecordingEventPublisher,
    SeqIdGenerator,
)
from tests.support.repositories import InMemoryUnitOfWork

T0 = datetime(2026, 3, 10, 12, 0, tzinfo=UTC)
W_SENDER = EntityId(str(UUID(int=1101)))
W_RECIPIENT = EntityId(str(UUID(int=1102)))


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


@pytest.fixture
def services(uow: InMemoryUnitOfWork) -> AppServices:
    return AppServices(
        uow=lambda: uow,
        clock=FixedClock(T0),
        ids=SeqIdGenerator(),
        events=RecordingEventPublisher(),
        idempotency=InMemoryIdempotencyStore(),
    )


def _transfer(uow: InMemoryUnitOfWork, *, n: int, amount: int, fee: int, at: datetime) -> None:
    sender_acc = uow.ledger.ensure_account(
        account_type=AccountType.CLIENT_LIABILITY, currency=XOF, owner_ref=f"user-{n}a"
    )
    recipient_acc = uow.ledger.ensure_account(
        account_type=AccountType.CLIENT_LIABILITY, currency=XOF, owner_ref=f"user-{n}b"
    )
    fee_acc = uow.ledger.ensure_account(
        account_type=AccountType.FLASH_FEE_INCOME, currency=XOF
    )
    uow.ledger.add(
        LedgerTransaction.transfer(
            id=EntityId(str(UUID(int=2000 + n))),
            occurred_at=at,
            reference=f"TRX-{n}",
            sender_account_id=sender_acc,
            sender_wallet_id=W_SENDER,
            recipient_account_id=recipient_acc,
            recipient_wallet_id=W_RECIPIENT,
            fee_income_account_id=fee_acc,
            amount=Money(amount, XOF),
            fee=Money(fee, XOF),
        )
    )


class TestTrialBalance:
    def test_balanced_by_currency(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _transfer(uow, n=1, amount=10_000, fee=80, at=T0)
        _transfer(uow, n=2, amount=5_000, fee=40, at=T0 + timedelta(hours=1))
        view = GetTrialBalance(services=services).execute(
            GetTrialBalanceCommand(as_of="2026-03-31T23:59:59+00:00")
        )
        assert view.balanced is True
        totals = view.totals_by_currency["XOF"]
        assert totals["debit_minor"] == totals["credit_minor"]
        assert totals["debit_minor"] == (10_000 + 80) + (5_000 + 40)
        # comptes non mouvementés absents
        assert all(r.debit_minor or r.credit_minor for r in view.rows)
        fee_rows = [r for r in view.rows if r.account_type == "FLASH_FEE_INCOME"]
        assert fee_rows[0].balance_minor == 120  # crédit - débit, sens normal CREDIT
        assert fee_rows[0].to_dict()["account_type"] == "FLASH_FEE_INCOME"

    def test_as_of_excludes_later_transactions(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _transfer(uow, n=1, amount=10_000, fee=0, at=T0)
        _transfer(uow, n=2, amount=99_999, fee=0, at=datetime(2026, 6, 1, tzinfo=UTC))
        view = GetTrialBalance(services=services).execute(
            GetTrialBalanceCommand(as_of="2026-03-31T00:00:00+00:00")
        )
        assert view.totals_by_currency["XOF"]["debit_minor"] == 10_000

    def test_empty_ledger_is_balanced(self, services: AppServices) -> None:
        view = GetTrialBalance(services=services).execute(
            GetTrialBalanceCommand(as_of="2026-03-31T00:00:00+00:00")
        )
        assert view.balanced is True and view.rows == []
        assert view.to_dict()["balanced"] is True

    def test_bad_date_rejected(self, services: AppServices) -> None:
        with pytest.raises(Exception, match="ISO 8601"):
            GetTrialBalance(services=services).execute(
                GetTrialBalanceCommand(as_of="pas une date")
            )

    def test_naive_date_is_accepted_as_utc(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _transfer(uow, n=1, amount=1_000, fee=0, at=T0)
        view = GetTrialBalance(services=services).execute(
            GetTrialBalanceCommand(as_of="2026-12-01T00:00:00")
        )
        assert view.balanced is True


class TestJournal:
    def test_lists_entries_in_window_chronologically(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _transfer(uow, n=1, amount=10_000, fee=80, at=T0 + timedelta(hours=2))
        _transfer(uow, n=2, amount=5_000, fee=0, at=T0)
        entries = GetLedgerJournal(services=services).execute(
            GetLedgerJournalCommand(
                start="2026-03-01T00:00:00+00:00", end="2026-04-01T00:00:00+00:00"
            )
        )
        assert [e.reference for e in entries] == ["TRX-2", "TRX-1"]
        assert entries[0].to_dict()["postings"][0]["direction"] in ("DEBIT", "CREDIT")

    def test_window_excludes_outside(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _transfer(uow, n=1, amount=10_000, fee=0, at=T0)
        entries = GetLedgerJournal(services=services).execute(
            GetLedgerJournalCommand(
                start="2025-01-01T00:00:00+00:00", end="2025-02-01T00:00:00+00:00"
            )
        )
        assert entries == []

    def test_bad_dates_rejected(self, services: AppServices) -> None:
        with pytest.raises(Exception, match="ISO 8601"):
            GetLedgerJournal(services=services).execute(
                GetLedgerJournalCommand(start="x", end="2026-01-01T00:00:00+00:00")
            )
        with pytest.raises(Exception, match="postérieur"):
            GetLedgerJournal(services=services).execute(
                GetLedgerJournalCommand(
                    start="2026-02-01T00:00:00+00:00", end="2026-01-01T00:00:00+00:00"
                )
            )


class TestMonthlyExport:
    def test_csv_one_row_per_posting(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _transfer(uow, n=1, amount=10_000, fee=80, at=T0)
        export = ExportMonthlyLedger(services=services).execute(
            ExportMonthlyLedgerCommand(year=2026, month=3)
        )
        assert export.media_type == "text/csv"
        assert export.filename == "flash-ledger-2026-03.csv"
        lines = export.content.decode().splitlines()
        assert lines[0].startswith("occurred_at,transaction_id,kind,reference")
        assert len(lines) == 1 + 3  # en-tête + 3 postings (débit, crédit, frais)

    def test_currency_filter(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _transfer(uow, n=1, amount=10_000, fee=0, at=T0)
        export = ExportMonthlyLedger(services=services).execute(
            ExportMonthlyLedgerCommand(year=2026, month=3, currency="xof")
        )
        assert export.filename.endswith("-XOF.csv")
        assert len(export.content.decode().splitlines()) == 1 + 2
        empty = ExportMonthlyLedger(services=services).execute(
            ExportMonthlyLedgerCommand(year=2026, month=3, currency="EUR")
        )
        assert len(empty.content.decode().splitlines()) == 1

    def test_december_rolls_to_next_year(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _transfer(uow, n=1, amount=1_000, fee=0, at=datetime(2026, 12, 15, tzinfo=UTC))
        export = ExportMonthlyLedger(services=services).execute(
            ExportMonthlyLedgerCommand(year=2026, month=12)
        )
        assert len(export.content.decode().splitlines()) == 1 + 2

    @pytest.mark.parametrize(
        ("year", "month"),
        [(2026, 0), (2026, 13), (1999, 6), (2200, 6)],
    )
    def test_bounds_rejected(
        self, services: AppServices, year: int, month: int
    ) -> None:
        with pytest.raises(Exception, match="hors bornes"):
            ExportMonthlyLedger(services=services).execute(
                ExportMonthlyLedgerCommand(year=year, month=month)
            )
