"""Relevé d'opérations d'un compte (BE-038).

Lecture directe du ledger (transactions touchant les portefeuilles de l'utilisateur),
projetée du point de vue du client : sens (entrée/sortie), montant, contrepartie, frais.
Pagination par curseur sur l'id de transaction (UUIDv7, donc trié dans le temps).

Une projection dédiée (``statement_entries``) accélérera et enrichira les filtres plus
tard sans changer ce contrat.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flash.application.services import AppServices
from flash.application.use_case import Command, UseCase
from flash.domain.ledger.chart import Direction
from flash.domain.ledger.transaction import LedgerTransaction
from flash.domain.shared.identifiers import EntityId

_MAX_LIMIT = 100
_DEFAULT_LIMIT = 20


@dataclass(frozen=True, slots=True)
class StatementLine:
    id: str
    reference: str
    kind: str
    direction: str  # "in" | "out"
    amount_minor: int  # variation nette du solde de l'utilisateur (valeur absolue)
    fee_minor: int  # frais supportés par l'utilisateur sur cette opération
    currency: str
    counterparty_masked: str | None
    note: str | None
    occurred_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "reference": self.reference,
            "kind": self.kind,
            "direction": self.direction,
            "amount_minor": self.amount_minor,
            "fee_minor": self.fee_minor,
            "currency": self.currency,
            "counterparty_masked": self.counterparty_masked,
            "note": self.note,
            "occurred_at": self.occurred_at,
        }


@dataclass(frozen=True, slots=True)
class ListStatementCommand(Command):
    user_id: str
    limit: int = _DEFAULT_LIMIT
    cursor: str | None = None


@dataclass(frozen=True, slots=True)
class StatementPage:
    lines: list[StatementLine]
    next_cursor: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "lines": [line.to_dict() for line in self.lines],
            "next_cursor": self.next_cursor,
        }


class ListStatement(UseCase[ListStatementCommand, StatementPage]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: ListStatementCommand) -> StatementPage:
        limit = max(1, min(command.limit, _MAX_LIMIT))
        before = EntityId(command.cursor) if command.cursor else None

        with self._services.uow() as uow:
            wallets = uow.wallets.list_for_user(EntityId(command.user_id))
            wallet_ids = [EntityId(str(w.id)) for w in wallets]
            if not wallet_ids:
                return StatementPage(lines=[], next_cursor=None)

            txns = uow.ledger.list_for_wallets(wallet_ids, limit=limit + 1, before=before)
            has_more = len(txns) > limit
            page = txns[:limit]
            wallet_id_set = {str(w) for w in wallet_ids}
            lines = [self._project(t, wallet_id_set) for t in page]
            next_cursor = str(page[-1].id) if has_more and page else None
            return StatementPage(lines=lines, next_cursor=next_cursor)

    def _project(self, txn: LedgerTransaction, wallet_ids: set[str]) -> StatementLine:
        mine = [
            p for p in txn.postings if p.wallet_id is not None and str(p.wallet_id) in wallet_ids
        ]
        net = 0
        currency = txn.postings[0].amount.currency.code
        for p in mine:
            currency = p.amount.currency.code
            net += (
                -p.amount.amount_minor if p.direction is Direction.DEBIT else p.amount.amount_minor
            )

        meta = dict(txn.metadata)
        is_out = net < 0
        fee_minor = int(meta.get("fee_minor", 0)) if is_out else 0
        gross = abs(net)
        # Pour une sortie, `net` inclut les frais : on isole le montant transféré.
        amount = gross - fee_minor if is_out else gross
        counterparty = meta.get("recipient_masked") if is_out else meta.get("sender_masked")

        return StatementLine(
            id=str(txn.id),
            reference=txn.reference,
            kind=txn.kind.value,
            direction="out" if is_out else "in",
            amount_minor=amount,
            fee_minor=fee_minor,
            currency=currency,
            counterparty_masked=counterparty,
            note=meta.get("note"),
            occurred_at=txn.occurred_at.isoformat(),
        )


__all__ = ["ListStatement", "ListStatementCommand", "StatementLine", "StatementPage"]
