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
from flash.domain.ledger.transaction import LedgerTransaction, TransactionKind
from flash.domain.shared.errors import WalletNotFound
from flash.domain.shared.identifiers import EntityId

_MAX_LIMIT = 100
_DEFAULT_LIMIT = 20

# Opérations où le payeur supporte lui-même les frais (débit = montant + frais).
_FEE_ON_PAYER = {
    TransactionKind.TRANSFER,
    TransactionKind.CASH_OUT,
    TransactionKind.OPERATOR_PAYOUT,
}


@dataclass(frozen=True, slots=True)
class _Projection:
    direction: str  # "in" | "out"
    amount_minor: int
    fee_minor: int
    currency: str
    counterparty_masked: str | None
    note: str | None


def _project_for_wallets(txn: LedgerTransaction, wallet_ids: set[str]) -> _Projection:
    """Projette une transaction du point de vue des portefeuilles de l'appelant."""
    mine = [p for p in txn.postings if p.wallet_id is not None and str(p.wallet_id) in wallet_ids]
    net = 0
    currency = txn.postings[0].amount.currency.code
    for p in mine:
        currency = p.amount.currency.code
        net += -p.amount.amount_minor if p.direction is Direction.DEBIT else p.amount.amount_minor

    meta = dict(txn.metadata)

    # Mouvement de coffre : les deux écritures portent le même portefeuille, le net est
    # nul. Le sens (vers / depuis le coffre) et le montant viennent des métadonnées.
    if txn.kind is TransactionKind.VAULT_MOVE:
        into_vault = bool(meta.get("into_vault"))
        moved = int(meta.get("amount_minor", 0))
        return _Projection(
            direction="out" if into_vault else "in",
            amount_minor=moved,
            fee_minor=0,
            currency=currency,
            counterparty_masked=meta.get("pocket_name"),
            note=meta.get("note"),
        )

    # Mouvements d'épargne : dépôt/retrait sont à net nul (deux écritures sur le même
    # portefeuille) ; la capitalisation d'intérêts est une entrée nette.
    if txn.kind in (TransactionKind.SAVINGS_DEPOSIT, TransactionKind.SAVINGS_WITHDRAWAL):
        return _Projection(
            direction="out" if txn.kind is TransactionKind.SAVINGS_DEPOSIT else "in",
            amount_minor=int(meta.get("amount_minor", 0)),
            fee_minor=0,
            currency=currency,
            counterparty_masked=meta.get("plan_name"),
            note=meta.get("note"),
        )
    if txn.kind is TransactionKind.INTEREST:
        return _Projection(
            direction="in",
            amount_minor=int(meta.get("amount_minor", abs(net))),
            fee_minor=0,
            currency=currency,
            counterparty_masked=meta.get("plan_name"),
            note=meta.get("note"),
        )

    is_out = net < 0
    gross = abs(net)
    meta_fee = int(meta.get("fee_minor", 0))
    # Les frais ne sont « supportés » par l'appelant que sur les sorties où son débit
    # les inclut (transfert, retrait). Sur un paiement marchand, la commission est
    # payée par le marchand : rien à isoler côté payeur.
    fee_minor = meta_fee if (is_out and txn.kind in _FEE_ON_PAYER) else 0
    amount = gross - fee_minor if is_out else gross

    counterparty = meta.get("recipient_masked") if is_out else meta.get("sender_masked")
    if counterparty is None:
        counterparty = (
            meta.get("merchant_name")
            or meta.get("client_masked")
            or meta.get("msisdn_masked")
        )

    return _Projection(
        direction="out" if is_out else "in",
        amount_minor=amount,
        fee_minor=fee_minor,
        currency=currency,
        counterparty_masked=counterparty,
        note=meta.get("note"),
    )


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
        p = _project_for_wallets(txn, wallet_ids)
        return StatementLine(
            id=str(txn.id),
            reference=txn.reference,
            kind=txn.kind.value,
            direction=p.direction,
            amount_minor=p.amount_minor,
            fee_minor=p.fee_minor,
            currency=p.currency,
            counterparty_masked=p.counterparty_masked,
            note=p.note,
            occurred_at=txn.occurred_at.isoformat(),
        )


# --------------------------------------------------------------------- reçu (BE-039)
@dataclass(frozen=True, slots=True)
class GetReceiptCommand(Command):
    user_id: str
    reference: str  # id de LedgerTransaction ou référence métier (« TRX-… », « MPY-… »…)


@dataclass(frozen=True, slots=True)
class ReceiptView:
    transaction_id: str
    reference: str
    kind: str
    direction: str  # "in" | "out"
    amount_minor: int
    fee_minor: int
    currency: str
    counterparty_masked: str | None
    note: str | None
    status: str  # "COMPLETED" | "REVERSED"
    occurred_at: str
    reversed_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "transaction_id": self.transaction_id,
            "reference": self.reference,
            "kind": self.kind,
            "direction": self.direction,
            "amount_minor": self.amount_minor,
            "fee_minor": self.fee_minor,
            "currency": self.currency,
            "counterparty_masked": self.counterparty_masked,
            "note": self.note,
            "status": self.status,
            "occurred_at": self.occurred_at,
            "reversed_at": self.reversed_at,
        }


class GetReceipt(UseCase[GetReceiptCommand, ReceiptView]):
    """Reçu détaillé d'une opération, du point de vue de l'appelant.

    L'appelant doit être partie prenante : l'un de ses portefeuilles est touché par la
    transaction. Sinon ``WalletNotFound`` (404, sans divulgation).
    """

    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: GetReceiptCommand) -> ReceiptView:
        with self._services.uow() as uow:
            wallets = uow.wallets.list_for_user(EntityId(command.user_id))
            wallet_ids = {str(w.id) for w in wallets}
            if not wallet_ids:
                raise WalletNotFound("Reçu introuvable.")

            txns = self._resolve(uow, command.reference)
            original = next((t for t in txns if t.kind is not TransactionKind.REVERSAL), None)
            reversal = next((t for t in txns if t.kind is TransactionKind.REVERSAL), None)
            if original is None:
                raise WalletNotFound("Reçu introuvable.")

            touched = any(
                p.wallet_id is not None and str(p.wallet_id) in wallet_ids
                for p in original.postings
            )
            if not touched:
                raise WalletNotFound("Reçu introuvable.")

            p = _project_for_wallets(original, wallet_ids)
            return ReceiptView(
                transaction_id=str(original.id),
                reference=original.reference,
                kind=original.kind.value,
                direction=p.direction,
                amount_minor=p.amount_minor,
                fee_minor=p.fee_minor,
                currency=p.currency,
                counterparty_masked=p.counterparty_masked,
                note=p.note,
                status="REVERSED" if reversal is not None else "COMPLETED",
                occurred_at=original.occurred_at.isoformat(),
                reversed_at=reversal.occurred_at.isoformat() if reversal is not None else None,
            )

    def _resolve(self, uow: Any, reference: str) -> list[LedgerTransaction]:
        try:
            txn_id = EntityId(reference)
        except ValueError:
            return list(uow.ledger.get_by_reference(reference))
        found = uow.ledger.get(txn_id)
        if found is None:
            return []
        return list(uow.ledger.get_by_reference(found.reference))


__all__ = [
    "GetReceipt",
    "GetReceiptCommand",
    "ListStatement",
    "ListStatementCommand",
    "ReceiptView",
    "StatementLine",
    "StatementPage",
]
