"""Agrégat ``MerchantCharge`` — un QR **dynamique** : le marchand fixe un montant et une
référence, avec expiration. Le client scanne et paie exactement ce montant.

``PENDING`` → ``PAID`` (paiement encaissé) / ``CANCELLED`` (marchand) / ``EXPIRED``.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from flash.domain.merchants.events import (
    MerchantChargeCancelled,
    MerchantChargeExpired,
    MerchantChargeOpened,
)
from flash.domain.shared.errors import InvalidAccountState, InvalidInput
from flash.domain.shared.events import EventRecorder
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import Money


class MerchantChargeStatus(StrEnum):
    PENDING = "PENDING"
    PAID = "PAID"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class MerchantCharge(EventRecorder):
    def __init__(
        self,
        *,
        id: EntityId,
        merchant_id: EntityId,
        amount: Money,
        currency_code: str,
        reference: str,
        status: MerchantChargeStatus,
        created_at: datetime,
        expires_at: datetime,
        paid_by: EntityId | None = None,
        ledger_transaction_id: EntityId | None = None,
    ) -> None:
        super().__init__()
        if amount.currency.code != currency_code:
            raise ValueError("Devise incohérente dans la demande marchand.")
        if not amount.is_positive:
            raise ValueError("Le montant doit être strictement positif.")
        if not reference.strip():
            raise InvalidInput("Une référence est requise pour un QR dynamique.")
        self.id = id
        self.merchant_id = merchant_id
        self.amount = amount
        self.currency_code = currency_code
        self.reference = reference.strip()
        self.status = status
        self.created_at = created_at
        self.expires_at = expires_at
        self.paid_by = paid_by
        self.ledger_transaction_id = ledger_transaction_id

    @classmethod
    def open(
        cls,
        *,
        charge_id: EntityId,
        merchant_id: EntityId,
        amount: Money,
        reference: str,
        now: datetime,
        expires_at: datetime,
    ) -> MerchantCharge:
        charge = cls(
            id=charge_id,
            merchant_id=merchant_id,
            amount=amount,
            currency_code=amount.currency.code,
            reference=reference,
            status=MerchantChargeStatus.PENDING,
            created_at=now,
            expires_at=expires_at,
        )
        charge.record_event(
            MerchantChargeOpened(
                occurred_at=now,
                aggregate_id=str(charge_id),
                merchant_id=str(merchant_id),
                amount_minor=amount.amount_minor,
                currency=amount.currency.code,
                reference=charge.reference,
            )
        )
        return charge

    def ensure_payable(self, now: datetime) -> None:
        if self.status is not MerchantChargeStatus.PENDING:
            raise InvalidAccountState(
                "Cette demande marchand n'est plus payable.", status=self.status.value
            )
        if now > self.expires_at:
            raise InvalidAccountState("Cette demande marchand a expiré.", status="EXPIRED")

    def mark_paid(self, *, payer_id: EntityId, ledger_transaction_id: EntityId) -> None:
        self.status = MerchantChargeStatus.PAID
        self.paid_by = payer_id
        self.ledger_transaction_id = ledger_transaction_id

    def cancel(self, now: datetime) -> None:
        if self.status is not MerchantChargeStatus.PENDING:
            raise InvalidAccountState(
                "Cette demande marchand ne peut plus être annulée.", status=self.status.value
            )
        self.status = MerchantChargeStatus.CANCELLED
        self.record_event(
            MerchantChargeCancelled(
                occurred_at=now, aggregate_id=str(self.id), merchant_id=str(self.merchant_id)
            )
        )

    def expire(self, now: datetime) -> None:
        if self.status is not MerchantChargeStatus.PENDING:
            return
        self.status = MerchantChargeStatus.EXPIRED
        self.record_event(
            MerchantChargeExpired(
                occurred_at=now, aggregate_id=str(self.id), merchant_id=str(self.merchant_id)
            )
        )

    def dynamic_qr_payload(self) -> str:
        return f"flash://pay?m={self.merchant_id}&c={self.id}"

    def __repr__(self) -> str:
        return (
            f"MerchantCharge(id={self.id!s}, {self.amount.amount_minor} "
            f"{self.currency_code}, status={self.status.value})"
        )


__all__ = ["MerchantCharge", "MerchantChargeStatus"]
