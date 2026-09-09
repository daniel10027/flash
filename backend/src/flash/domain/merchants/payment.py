"""Agrégat ``MerchantPayment`` — trace d'un paiement marchand encaissé.

``COMPLETED`` à la création ; ``REFUNDED`` par une contre-passation (``BE-037``).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from flash.domain.merchants.events import MerchantPaymentCompleted, MerchantPaymentRefunded
from flash.domain.shared.errors import InvalidAccountState
from flash.domain.shared.events import EventRecorder
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import Money


class MerchantPaymentStatus(StrEnum):
    COMPLETED = "COMPLETED"
    REFUNDED = "REFUNDED"


class MerchantPayment(EventRecorder):
    def __init__(
        self,
        *,
        id: EntityId,
        payer_id: EntityId,
        merchant_id: EntityId,
        amount: Money,
        fee: Money,
        currency_code: str,
        reference: str,
        status: MerchantPaymentStatus,
        ledger_transaction_id: EntityId,
        created_at: datetime,
        charge_id: EntityId | None = None,
        settlement_id: EntityId | None = None,
        sub_account_id: EntityId | None = None,
    ) -> None:
        super().__init__()
        if amount.currency.code != currency_code or fee.currency.code != currency_code:
            raise ValueError("Devises incohérentes dans le paiement marchand.")
        if not amount.is_positive:
            raise ValueError("Le montant doit être strictement positif.")
        if fee.is_negative or fee > amount:
            raise ValueError("Commission marchand invalide.")
        self.id = id
        self.payer_id = payer_id
        self.merchant_id = merchant_id
        self.amount = amount
        self.fee = fee
        self.currency_code = currency_code
        self.reference = reference
        self.status = status
        self.ledger_transaction_id = ledger_transaction_id
        self.created_at = created_at
        self.charge_id = charge_id
        self.settlement_id = settlement_id
        self.sub_account_id = sub_account_id

    @classmethod
    def record(
        cls,
        *,
        payment_id: EntityId,
        payer_id: EntityId,
        merchant_id: EntityId,
        amount: Money,
        fee: Money,
        reference: str,
        ledger_transaction_id: EntityId,
        now: datetime,
        charge_id: EntityId | None = None,
        sub_account_id: EntityId | None = None,
    ) -> MerchantPayment:
        payment = cls(
            id=payment_id,
            payer_id=payer_id,
            merchant_id=merchant_id,
            amount=amount,
            fee=fee,
            currency_code=amount.currency.code,
            reference=reference,
            status=MerchantPaymentStatus.COMPLETED,
            ledger_transaction_id=ledger_transaction_id,
            created_at=now,
            charge_id=charge_id,
            sub_account_id=sub_account_id,
        )
        payment.record_event(
            MerchantPaymentCompleted(
                occurred_at=now,
                aggregate_id=str(payment_id),
                payer_id=str(payer_id),
                merchant_id=str(merchant_id),
                amount_minor=amount.amount_minor,
                fee_minor=fee.amount_minor,
                currency=amount.currency.code,
                reference=reference,
            )
        )
        return payment

    def refund(self, *, reversal_transaction_id: EntityId, now: datetime) -> None:
        if self.status is not MerchantPaymentStatus.COMPLETED:
            raise InvalidAccountState(
                "Ce paiement marchand ne peut pas être remboursé.", status=self.status.value
            )
        self.status = MerchantPaymentStatus.REFUNDED
        self.record_event(
            MerchantPaymentRefunded(
                occurred_at=now,
                aggregate_id=str(self.id),
                payer_id=str(self.payer_id),
                merchant_id=str(self.merchant_id),
                amount_minor=self.amount.amount_minor,
                fee_minor=self.fee.amount_minor,
                currency=self.currency_code,
                reference=self.reference,
                reversal_transaction_id=str(reversal_transaction_id),
            )
        )

    @property
    def net_to_merchant(self) -> Money:
        return self.amount - self.fee

    @property
    def is_settleable(self) -> bool:
        return self.status is MerchantPaymentStatus.COMPLETED and self.settlement_id is None

    def attach_settlement(self, settlement_id: EntityId) -> None:
        if self.settlement_id is not None:
            raise InvalidAccountState("Ce paiement est déjà rattaché à un règlement.")
        self.settlement_id = settlement_id

    def __repr__(self) -> str:
        return (
            f"MerchantPayment(id={self.id!s}, {self.amount.amount_minor} "
            f"{self.currency_code}, status={self.status.value})"
        )


__all__ = ["MerchantPayment", "MerchantPaymentStatus"]
