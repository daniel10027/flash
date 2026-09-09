"""Exports réglementaires & comptables (BE-077).

* ``GetTrialBalance`` — balance générale à une date : par compte du plan, cumul débit /
  crédit et solde signé (sens normal). **Contrôle : par devise, Σ débits = Σ crédits.**
* ``GetLedgerJournal`` — journal chronologique des écritures sur une période.
* ``ExportMonthlyLedger`` — CSV d'un mois calendaire (une ligne par posting), filtrable
  par devise (proxy de zone : XOF = UEMOA, XAF = CEMAC).
"""

from __future__ import annotations

import csv
import io
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from flash.application.services import AppServices
from flash.application.use_case import Command, UseCase
from flash.domain.ledger.chart import Direction, normal_balance
from flash.domain.shared.errors import InvalidInput

_EPOCH = datetime(2000, 1, 1, tzinfo=UTC)


def _parse_instant(raw: str, *, field: str) -> datetime:
    try:
        value = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise InvalidInput(f"`{field}` : date/heure ISO 8601 attendue.") from exc
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


# ============================================================== balance générale
@dataclass(frozen=True, slots=True)
class TrialBalanceRow:
    account_id: str
    account_type: str
    currency: str
    owner_ref: str | None
    debit_minor: int
    credit_minor: int
    balance_minor: int  # solde signé dans le sens normal du compte

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "account_type": self.account_type,
            "currency": self.currency,
            "owner_ref": self.owner_ref,
            "debit_minor": self.debit_minor,
            "credit_minor": self.credit_minor,
            "balance_minor": self.balance_minor,
        }


@dataclass(frozen=True, slots=True)
class TrialBalance:
    as_of: str
    rows: list[TrialBalanceRow]
    totals_by_currency: dict[str, dict[str, int]]
    balanced: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of,
            "balanced": self.balanced,
            "totals_by_currency": self.totals_by_currency,
            "rows": [r.to_dict() for r in self.rows],
        }


@dataclass(frozen=True, slots=True)
class GetTrialBalanceCommand(Command):
    as_of: str


class GetTrialBalance(UseCase[GetTrialBalanceCommand, TrialBalance]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: GetTrialBalanceCommand) -> TrialBalance:
        as_of = _parse_instant(command.as_of, field="as_of")
        with self._services.uow() as uow:
            accounts = uow.ledger.list_accounts()
            sums: dict[str, list[int]] = defaultdict(lambda: [0, 0])
            for txn in uow.ledger.list_between(_EPOCH, as_of + timedelta(microseconds=1)):
                for p in txn.postings:
                    bucket = sums[str(p.account_id)]
                    if p.direction is Direction.DEBIT:
                        bucket[0] += p.amount.amount_minor
                    else:
                        bucket[1] += p.amount.amount_minor

        rows: list[TrialBalanceRow] = []
        totals: dict[str, dict[str, int]] = defaultdict(
            lambda: {"debit_minor": 0, "credit_minor": 0}
        )
        for acc in sorted(accounts, key=lambda a: (a.type.value, a.currency.code, str(a.id))):
            debit, credit = sums.get(str(acc.id), [0, 0])
            if debit == 0 and credit == 0:
                continue
            signed = (
                debit - credit
                if normal_balance(acc.type) is Direction.DEBIT
                else credit - debit
            )
            rows.append(
                TrialBalanceRow(
                    account_id=str(acc.id),
                    account_type=acc.type.value,
                    currency=acc.currency.code,
                    owner_ref=acc.owner_ref,
                    debit_minor=debit,
                    credit_minor=credit,
                    balance_minor=signed,
                )
            )
            totals[acc.currency.code]["debit_minor"] += debit
            totals[acc.currency.code]["credit_minor"] += credit

        balanced = all(
            t["debit_minor"] == t["credit_minor"] for t in totals.values()
        )
        return TrialBalance(
            as_of=as_of.isoformat(),
            rows=rows,
            totals_by_currency=dict(totals),
            balanced=balanced,
        )


# ============================================================== journal
@dataclass(frozen=True, slots=True)
class JournalPosting:
    account_id: str
    direction: str
    amount_minor: int
    currency: str
    wallet_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "account_id": self.account_id,
            "direction": self.direction,
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "wallet_id": self.wallet_id,
        }


@dataclass(frozen=True, slots=True)
class JournalEntry:
    transaction_id: str
    kind: str
    reference: str
    occurred_at: str
    postings: list[JournalPosting]

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "kind": self.kind,
            "reference": self.reference,
            "occurred_at": self.occurred_at,
            "postings": [p.to_dict() for p in self.postings],
        }


@dataclass(frozen=True, slots=True)
class GetLedgerJournalCommand(Command):
    start: str
    end: str
    limit: int = 1_000


class GetLedgerJournal(UseCase[GetLedgerJournalCommand, list[JournalEntry]]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: GetLedgerJournalCommand) -> list[JournalEntry]:
        start = _parse_instant(command.start, field="start")
        end = _parse_instant(command.end, field="end")
        if end <= start:
            raise InvalidInput("`end` doit être postérieur à `start`.")
        limit = max(1, min(command.limit, 5_000))
        with self._services.uow() as uow:
            txns = uow.ledger.list_between(start, end, limit=limit)
        return [
            JournalEntry(
                transaction_id=str(t.id),
                kind=t.kind.value,
                reference=t.reference,
                occurred_at=t.occurred_at.isoformat(),
                postings=[
                    JournalPosting(
                        account_id=str(p.account_id),
                        direction=p.direction.value,
                        amount_minor=p.amount.amount_minor,
                        currency=p.amount.currency.code,
                        wallet_id=str(p.wallet_id) if p.wallet_id else None,
                    )
                    for p in t.postings
                ],
            )
            for t in txns
        ]


# ============================================================== export mensuel
@dataclass(frozen=True, slots=True)
class MonthlyLedgerExport:
    content: bytes
    media_type: str
    filename: str


@dataclass(frozen=True, slots=True)
class ExportMonthlyLedgerCommand(Command):
    year: int
    month: int
    currency: str | None = None


class ExportMonthlyLedger(
    UseCase[ExportMonthlyLedgerCommand, MonthlyLedgerExport]
):
    _COLUMNS = (
        "occurred_at",
        "transaction_id",
        "kind",
        "reference",
        "account_id",
        "direction",
        "currency",
        "amount_minor",
        "wallet_id",
    )

    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(
        self, command: ExportMonthlyLedgerCommand
    ) -> MonthlyLedgerExport:
        if not 1 <= command.month <= 12:
            raise InvalidInput("Mois hors bornes (1 à 12).")
        if not 2000 <= command.year <= 2100:
            raise InvalidInput("Année hors bornes.")
        start = datetime(command.year, command.month, 1, tzinfo=UTC)
        end = (
            datetime(command.year + 1, 1, 1, tzinfo=UTC)
            if command.month == 12
            else datetime(command.year, command.month + 1, 1, tzinfo=UTC)
        )
        wanted = command.currency.upper() if command.currency else None

        with self._services.uow() as uow:
            txns = uow.ledger.list_between(start, end)

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(self._COLUMNS)
        for t in txns:
            for p in t.postings:
                ccy = p.amount.currency.code
                if wanted is not None and ccy != wanted:
                    continue
                writer.writerow(
                    [
                        t.occurred_at.isoformat(),
                        str(t.id),
                        t.kind.value,
                        t.reference,
                        str(p.account_id),
                        p.direction.value,
                        ccy,
                        p.amount.amount_minor,
                        str(p.wallet_id) if p.wallet_id else "",
                    ]
                )
        suffix = f"-{wanted}" if wanted else ""
        return MonthlyLedgerExport(
            content=buffer.getvalue().encode("utf-8"),
            media_type="text/csv",
            filename=f"flash-ledger-{command.year:04d}-{command.month:02d}{suffix}.csv",
        )


__all__ = [
    "ExportMonthlyLedger",
    "ExportMonthlyLedgerCommand",
    "GetLedgerJournal",
    "GetLedgerJournalCommand",
    "GetTrialBalance",
    "GetTrialBalanceCommand",
    "JournalEntry",
    "JournalPosting",
    "MonthlyLedgerExport",
    "TrialBalance",
    "TrialBalanceRow",
]
