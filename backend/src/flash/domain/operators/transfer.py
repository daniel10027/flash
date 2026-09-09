"""Agrégat ``OperatorTransfer`` — un envoi (``PAYOUT``) ou une réception (``COLLECT``)
entre un portefeuille Flash et un compte d'opérateur mobile money (BE-064 → BE-067).

L'opération est **asynchrone** : elle est créée ``PENDING`` (fonds réservés côté payout)
puis résolue ``SUCCEEDED`` / ``FAILED`` par le webhook de l'opérateur. La résolution est
idempotente : rejouer un callback déjà appliqué ne fait rien.

Comptablement, le transit passe par ``OPERATOR_SUSPENSE`` :
- ``PAYOUT`` : le client paie ``amount + fee`` ; ``amount`` va au suspense, ``fee`` à Flash.
- ``COLLECT`` : le suspense reçoit ``amount`` ; le client est crédité ``amount - fee``.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from flash.domain.operators.events import (
    OperatorTransferFailed,
    OperatorTransferInitiated,
    OperatorTransferSucceeded,
)
from flash.domain.shared.errors import InvalidInput, OperatorTransferNotResolvable
from flash.domain.shared.events import EventRecorder
from flash.domain.shared.identifiers import EntityId, Msisdn
from flash.domain.shared.money import Money


class OperatorTransferDirection(StrEnum):
    PAYOUT = "PAYOUT"  # Flash -> opérateur
    COLLECT = "COLLECT"  # opérateur -> Flash


class OperatorTransferStatus(StrEnum):
    PENDING = "PENDING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"


class OperatorTransfer(EventRecorder):
    def __init__(
        self,
        *,
        id: EntityId,
        user_id: EntityId,
        wallet_id: EntityId,
        operator: str,
        direction: OperatorTransferDirection,
        msisdn: Msisdn,
        amount: Money,
        fee: Money,
        reference: str,
        status: OperatorTransferStatus,
        created_at: datetime,
        currency_code: str | None = None,
        external_ref: str | None = None,
        failure_reason: str | None = None,
        resolved_at: datetime | None = None,
        ledger_transaction_id: EntityId | None = None,
    ) -> None:
        super().__init__()
        if amount.currency != fee.currency:
            raise InvalidInput("Montant et frais dans des devises différentes.")
        if not amount.is_positive:
            raise InvalidInput("Le montant doit être strictement positif.")
        if fee.is_negative:
            raise InvalidInput("Les frais ne peuvent pas être négatifs.")
        self.id = id
        self.user_id = user_id
        self.wallet_id = wallet_id
        self.operator = operator
        self.direction = direction
        self.msisdn = msisdn
        self.amount = amount
        self.fee = fee
        self.reference = reference
        self.status = status
        self.created_at = created_at
        self.currency_code = currency_code or amount.currency.code
        self.external_ref = external_ref
        self.failure_reason = failure_reason
        self.resolved_at = resolved_at
        self.ledger_transaction_id = ledger_transaction_id

    # ---------------------------------------------------------------- fabriques
    @classmethod
    def start(
        cls,
        *,
        transfer_id: EntityId,
        user_id: EntityId,
        wallet_id: EntityId,
        operator: str,
        direction: OperatorTransferDirection,
        msisdn: Msisdn,
        amount: Money,
        fee: Money,
        reference: str,
        now: datetime,
    ) -> OperatorTransfer:
        transfer = cls(
            id=transfer_id,
            user_id=user_id,
            wallet_id=wallet_id,
            operator=operator,
            direction=direction,
            msisdn=msisdn,
            amount=amount,
            fee=fee,
            reference=reference,
            status=OperatorTransferStatus.PENDING,
            created_at=now,
        )
        transfer.record_event(
            OperatorTransferInitiated(
                occurred_at=now,
                aggregate_id=str(transfer_id),
                user_id=str(user_id),
                wallet_id=str(wallet_id),
                operator=operator,
                direction=direction.value,
                msisdn_masked=msisdn.masked(),
                amount_minor=amount.amount_minor,
                currency=amount.currency.code,
                reference=reference,
            )
        )
        return transfer

    # ---------------------------------------------------------------- lecture
    @property
    def is_pending(self) -> bool:
        return self.status is OperatorTransferStatus.PENDING

    @property
    def debit_total(self) -> Money:
        """Ce que le portefeuille supporte pour un payout : ``amount + fee``."""
        return self.amount + self.fee

    @property
    def credit_net(self) -> Money:
        """Ce que le portefeuille reçoit pour un collect : ``amount - fee``."""
        return self.amount - self.fee

    def attach_external_ref(self, external_ref: str) -> None:
        self.external_ref = external_ref

    # ---------------------------------------------------------------- résolution
    def mark_succeeded(
        self, *, external_ref: str | None, ledger_transaction_id: EntityId, now: datetime
    ) -> None:
        self._ensure_pending()
        if external_ref:
            self.external_ref = external_ref
        self.status = OperatorTransferStatus.SUCCEEDED
        self.ledger_transaction_id = ledger_transaction_id
        self.resolved_at = now
        self.record_event(
            OperatorTransferSucceeded(
                occurred_at=now,
                aggregate_id=str(self.id),
                user_id=str(self.user_id),
                wallet_id=str(self.wallet_id),
                operator=self.operator,
                direction=self.direction.value,
                msisdn_masked=self.msisdn.masked(),
                amount_minor=self.amount.amount_minor,
                fee_minor=self.fee.amount_minor,
                currency=self.currency_code,
                reference=self.reference,
            )
        )

    def mark_failed(self, *, reason: str, now: datetime) -> None:
        self._ensure_pending()
        self.status = OperatorTransferStatus.FAILED
        self.failure_reason = reason
        self.resolved_at = now
        self.record_event(
            OperatorTransferFailed(
                occurred_at=now,
                aggregate_id=str(self.id),
                user_id=str(self.user_id),
                wallet_id=str(self.wallet_id),
                operator=self.operator,
                direction=self.direction.value,
                amount_minor=self.amount.amount_minor,
                currency=self.currency_code,
                reference=self.reference,
                reason=reason,
            )
        )

    def _ensure_pending(self) -> None:
        if not self.is_pending:
            raise OperatorTransferNotResolvable(reference=self.reference, status=self.status.value)

    def __repr__(self) -> str:
        return (
            f"OperatorTransfer({self.direction.value}, {self.operator}, "
            f"{self.amount}, status={self.status.value})"
        )


__all__ = ["OperatorTransfer", "OperatorTransferDirection", "OperatorTransferStatus"]
