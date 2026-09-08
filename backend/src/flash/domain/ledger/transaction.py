"""``Posting`` et ``LedgerTransaction`` — écritures du ledger en partie double.

Une ``LedgerTransaction`` est **immuable** et **équilibrée par construction** : pour
chaque devise présente, la somme des débits égale la somme des crédits. Toute tentative
d'instancier une transaction déséquilibrée lève ``LedgerImbalance`` (erreur de
programmation, pas une condition métier attendue).

Les corrections se font par une transaction ``REVERSAL`` (voir ``reversal``), jamais par
modification ou suppression.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from types import MappingProxyType
from typing import Any

from flash.domain.ledger.chart import Direction
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import Money


class LedgerImbalance(Exception):
    """Levée quand les postings d'une transaction ne s'équilibrent pas."""


class TransactionKind(StrEnum):
    TRANSFER = "TRANSFER"
    FEE = "FEE"
    CASH_IN = "CASH_IN"
    CASH_OUT = "CASH_OUT"
    VAULT_MOVE = "VAULT_MOVE"
    SAVINGS_DEPOSIT = "SAVINGS_DEPOSIT"
    SAVINGS_WITHDRAWAL = "SAVINGS_WITHDRAWAL"
    INTEREST = "INTEREST"
    CARD_AUTH = "CARD_AUTH"
    CARD_CAPTURE = "CARD_CAPTURE"
    CARD_REFUND = "CARD_REFUND"
    OPERATOR_PAYOUT = "OPERATOR_PAYOUT"
    OPERATOR_COLLECT = "OPERATOR_COLLECT"
    MERCHANT_SETTLEMENT = "MERCHANT_SETTLEMENT"
    AGENT_FLOAT_TOPUP = "AGENT_FLOAT_TOPUP"
    AGENT_COMMISSION_PAYOUT = "AGENT_COMMISSION_PAYOUT"
    REVERSAL = "REVERSAL"
    ADJUSTMENT = "ADJUSTMENT"


@dataclass(frozen=True, slots=True)
class Posting:
    """Une ligne d'écriture : un compte, un sens, un montant strictement positif."""

    account_id: EntityId
    direction: Direction
    amount: Money
    wallet_id: EntityId | None = None
    analytic: str | None = None

    def __post_init__(self) -> None:
        if not self.amount.is_positive:
            raise LedgerImbalance("Le montant d'un posting doit être strictement positif.")

    def mirror(self) -> Posting:
        """Posting opposé (même compte, sens inversé) — utilisé pour les reversals."""
        return Posting(
            account_id=self.account_id,
            direction=self.direction.opposite,
            amount=self.amount,
            wallet_id=self.wallet_id,
            analytic=self.analytic,
        )


def _debit(account_id: EntityId, amount: Money, **kw: Any) -> Posting:
    return Posting(account_id=account_id, direction=Direction.DEBIT, amount=amount, **kw)


def _credit(account_id: EntityId, amount: Money, **kw: Any) -> Posting:
    return Posting(account_id=account_id, direction=Direction.CREDIT, amount=amount, **kw)


@dataclass(frozen=True, slots=True)
class LedgerTransaction:
    id: EntityId
    kind: TransactionKind
    postings: tuple[Posting, ...]
    occurred_at: datetime
    reference: str
    reason: str
    metadata: Mapping[str, Any] = field(default_factory=dict)
    reverses_transaction_id: EntityId | None = None

    def __post_init__(self) -> None:
        if len(self.postings) < 2:
            raise LedgerImbalance("Une transaction doit comporter au moins deux postings.")
        for currency_code, (debits, credits) in self._totals().items():
            if debits != credits:
                raise LedgerImbalance(
                    f"Transaction déséquilibrée en {currency_code} : "
                    f"débits={debits}, crédits={credits}."
                )
        object.__setattr__(self, "postings", tuple(self.postings))
        object.__setattr__(self, "metadata", MappingProxyType(dict(self.metadata)))

    def _totals(self) -> dict[str, tuple[int, int]]:
        acc: dict[str, list[int]] = {}
        for p in self.postings:
            slot = acc.setdefault(p.amount.currency.code, [0, 0])
            if p.direction is Direction.DEBIT:
                slot[0] += p.amount.amount_minor
            else:
                slot[1] += p.amount.amount_minor
        return {code: (d, c) for code, (d, c) in acc.items()}

    @property
    def is_balanced(self) -> bool:
        return all(d == c for d, c in self._totals().values())

    def total_amount(self) -> Money:
        """Montant « nominal » de la transaction : somme des débits (mono-devise)."""
        totals = self._totals()
        if len(totals) != 1:
            raise ValueError("total_amount() n'a de sens que pour une transaction mono-devise.")
        (code, (debits, _)) = next(iter(totals.items()))
        sample = next(p.amount for p in self.postings if p.amount.currency.code == code)
        return sample.with_amount(debits)

    # ------------------------------------------------------------- fabriques
    @staticmethod
    def transfer(
        *,
        id: EntityId,
        occurred_at: datetime,
        reference: str,
        sender_account_id: EntityId,
        sender_wallet_id: EntityId,
        recipient_account_id: EntityId,
        recipient_wallet_id: EntityId,
        fee_income_account_id: EntityId,
        amount: Money,
        fee: Money,
        metadata: Mapping[str, Any] | None = None,
    ) -> LedgerTransaction:
        """Transfert P2P : l'émetteur paie ``amount + fee``, le destinataire reçoit
        ``amount``, Flash encaisse ``fee``."""
        postings = [
            _debit(sender_account_id, amount + fee, wallet_id=sender_wallet_id),
            _credit(recipient_account_id, amount, wallet_id=recipient_wallet_id),
        ]
        if fee.is_positive:
            postings.append(_credit(fee_income_account_id, fee))
        return LedgerTransaction(
            id=id,
            kind=TransactionKind.TRANSFER,
            postings=tuple(postings),
            occurred_at=occurred_at,
            reference=reference,
            reason="Transfert entre comptes Flash",
            metadata=metadata or {},
        )

    @staticmethod
    def fee(
        *,
        id: EntityId,
        occurred_at: datetime,
        reference: str,
        source_account_id: EntityId,
        source_wallet_id: EntityId,
        fee_income_account_id: EntityId,
        fee: Money,
        reason: str = "Frais Flash",
        metadata: Mapping[str, Any] | None = None,
    ) -> LedgerTransaction:
        return LedgerTransaction(
            id=id,
            kind=TransactionKind.FEE,
            postings=(
                _debit(source_account_id, fee, wallet_id=source_wallet_id),
                _credit(fee_income_account_id, fee),
            ),
            occurred_at=occurred_at,
            reference=reference,
            reason=reason,
            metadata=metadata or {},
        )

    @staticmethod
    def cash_in(
        *,
        id: EntityId,
        occurred_at: datetime,
        reference: str,
        agent_float_account_id: EntityId,
        client_account_id: EntityId,
        client_wallet_id: EntityId,
        amount: Money,
        commission: Money | None = None,
        agent_commission_expense_account_id: EntityId | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> LedgerTransaction:
        """Dépôt cash : l'agent remet de l'e-money (float ↓) au client (dette Flash ↑)."""
        postings = [
            _debit(agent_float_account_id, amount),
            _credit(client_account_id, amount, wallet_id=client_wallet_id),
        ]
        postings += _commission_postings(
            commission, agent_commission_expense_account_id, agent_float_account_id
        )
        return LedgerTransaction(
            id=id,
            kind=TransactionKind.CASH_IN,
            postings=tuple(postings),
            occurred_at=occurred_at,
            reference=reference,
            reason="Dépôt cash en agence",
            metadata=metadata or {},
        )

    @staticmethod
    def cash_out(
        *,
        id: EntityId,
        occurred_at: datetime,
        reference: str,
        client_account_id: EntityId,
        client_wallet_id: EntityId,
        agent_float_account_id: EntityId,
        fee_income_account_id: EntityId,
        amount: Money,
        fee: Money,
        commission: Money | None = None,
        agent_commission_expense_account_id: EntityId | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> LedgerTransaction:
        """Retrait cash : le client paie ``amount + fee``, l'agent reprend l'e-money
        (float ↑ de ``amount``), Flash encaisse ``fee``."""
        postings = [
            _debit(client_account_id, amount + fee, wallet_id=client_wallet_id),
            _credit(agent_float_account_id, amount),
        ]
        if fee.is_positive:
            postings.append(_credit(fee_income_account_id, fee))
        postings += _commission_postings(
            commission, agent_commission_expense_account_id, agent_float_account_id
        )
        return LedgerTransaction(
            id=id,
            kind=TransactionKind.CASH_OUT,
            postings=tuple(postings),
            occurred_at=occurred_at,
            reference=reference,
            reason="Retrait cash en agence",
            metadata=metadata or {},
        )

    @staticmethod
    def _move_between(
        *,
        id: EntityId,
        kind: TransactionKind,
        occurred_at: datetime,
        reference: str,
        reason: str,
        from_account_id: EntityId,
        to_account_id: EntityId,
        wallet_id: EntityId,
        amount: Money,
        analytic: str | None,
        metadata: Mapping[str, Any] | None = None,
    ) -> LedgerTransaction:
        return LedgerTransaction(
            id=id,
            kind=kind,
            postings=(
                _debit(from_account_id, amount, wallet_id=wallet_id, analytic=analytic),
                _credit(to_account_id, amount, wallet_id=wallet_id, analytic=analytic),
            ),
            occurred_at=occurred_at,
            reference=reference,
            reason=reason,
            metadata=metadata or {},
        )

    @classmethod
    def vault_move(
        cls,
        *,
        id: EntityId,
        occurred_at: datetime,
        reference: str,
        client_account_id: EntityId,
        savings_account_id: EntityId,
        wallet_id: EntityId,
        pocket_ref: str,
        amount: Money,
        into_vault: bool,
        metadata: Mapping[str, Any] | None = None,
    ) -> LedgerTransaction:
        """Déplacement instantané et sans frais entre le disponible et une poche de coffre."""
        src, dst = (
            (client_account_id, savings_account_id)
            if into_vault
            else (savings_account_id, client_account_id)
        )
        return cls._move_between(
            id=id,
            kind=TransactionKind.VAULT_MOVE,
            occurred_at=occurred_at,
            reference=reference,
            reason="Alimentation du coffre" if into_vault else "Retrait du coffre",
            from_account_id=src,
            to_account_id=dst,
            wallet_id=wallet_id,
            amount=amount,
            analytic=pocket_ref,
            metadata=metadata,
        )

    @classmethod
    def savings_deposit(
        cls,
        *,
        id: EntityId,
        occurred_at: datetime,
        reference: str,
        client_account_id: EntityId,
        savings_account_id: EntityId,
        wallet_id: EntityId,
        plan_ref: str,
        amount: Money,
        metadata: Mapping[str, Any] | None = None,
    ) -> LedgerTransaction:
        return cls._move_between(
            id=id,
            kind=TransactionKind.SAVINGS_DEPOSIT,
            occurred_at=occurred_at,
            reference=reference,
            reason="Versement sur un plan d'épargne",
            from_account_id=client_account_id,
            to_account_id=savings_account_id,
            wallet_id=wallet_id,
            amount=amount,
            analytic=plan_ref,
            metadata=metadata,
        )

    @classmethod
    def savings_withdrawal(
        cls,
        *,
        id: EntityId,
        occurred_at: datetime,
        reference: str,
        client_account_id: EntityId,
        savings_account_id: EntityId,
        wallet_id: EntityId,
        plan_ref: str,
        amount: Money,
        metadata: Mapping[str, Any] | None = None,
    ) -> LedgerTransaction:
        return cls._move_between(
            id=id,
            kind=TransactionKind.SAVINGS_WITHDRAWAL,
            occurred_at=occurred_at,
            reference=reference,
            reason="Clôture / retrait d'un plan d'épargne",
            from_account_id=savings_account_id,
            to_account_id=client_account_id,
            wallet_id=wallet_id,
            amount=amount,
            analytic=plan_ref,
            metadata=metadata,
        )

    @staticmethod
    def agent_float_topup(
        *,
        id: EntityId,
        occurred_at: datetime,
        reference: str,
        bank_settlement_account_id: EntityId,
        agent_float_account_id: EntityId,
        amount: Money,
        metadata: Mapping[str, Any] | None = None,
    ) -> LedgerTransaction:
        """L'agent achète de l'e-money : trésorerie Flash ↑, float de l'agent ↑."""
        return LedgerTransaction(
            id=id,
            kind=TransactionKind.AGENT_FLOAT_TOPUP,
            postings=(
                _debit(bank_settlement_account_id, amount),
                _credit(agent_float_account_id, amount),
            ),
            occurred_at=occurred_at,
            reference=reference,
            reason="Approvisionnement du float agent",
            metadata=metadata or {},
        )

    @staticmethod
    def interest(
        *,
        id: EntityId,
        occurred_at: datetime,
        reference: str,
        interest_expense_account_id: EntityId,
        savings_account_id: EntityId,
        wallet_id: EntityId,
        plan_ref: str,
        amount: Money,
        metadata: Mapping[str, Any] | None = None,
    ) -> LedgerTransaction:
        """Capitalisation d'intérêts : charge pour Flash, dette d'épargne pour le client."""
        return LedgerTransaction(
            id=id,
            kind=TransactionKind.INTEREST,
            postings=(
                _debit(interest_expense_account_id, amount),
                _credit(savings_account_id, amount, wallet_id=wallet_id, analytic=plan_ref),
            ),
            occurred_at=occurred_at,
            reference=reference,
            reason="Intérêts d'épargne",
            metadata=metadata or {},
        )

    @staticmethod
    def reversal(
        *,
        id: EntityId,
        original: LedgerTransaction,
        occurred_at: datetime,
        reason: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> LedgerTransaction:
        """Contre-passation : chaque posting de ``original`` est inversé."""
        if original.kind is TransactionKind.REVERSAL:
            raise LedgerImbalance("On ne contre-passe pas une contre-passation.")
        return LedgerTransaction(
            id=id,
            kind=TransactionKind.REVERSAL,
            postings=tuple(p.mirror() for p in original.postings),
            occurred_at=occurred_at,
            reference=original.reference,
            reason=reason,
            metadata=metadata or {},
            reverses_transaction_id=original.id,
        )


def _commission_postings(
    commission: Money | None,
    expense_account_id: EntityId | None,
    agent_float_account_id: EntityId,
) -> list[Posting]:
    if commission is None or commission.is_zero:
        return []
    if expense_account_id is None:
        raise LedgerImbalance(
            "Compte de charge de commission requis quand une commission est fournie."
        )
    return [
        _debit(expense_account_id, commission),
        _credit(agent_float_account_id, commission),
    ]


def sum_postings(postings: Iterable[Posting]) -> dict[str, int]:
    """Solde net signé par devise (positif = débit net). Utilitaire de test/contrôle."""
    net: dict[str, int] = {}
    for p in postings:
        delta = p.amount.amount_minor if p.direction is Direction.DEBIT else -p.amount.amount_minor
        net[p.amount.currency.code] = net.get(p.amount.currency.code, 0) + delta
    return net


__all__ = [
    "LedgerImbalance",
    "LedgerTransaction",
    "Posting",
    "TransactionKind",
    "sum_postings",
]
