"""Agrégat ``MerchantSettlement`` — un règlement périodique vers le compte bancaire d'un
marchand (BE-070).

Il agrège le **net** (``amount - fee``) des ``MerchantPayment`` ``COMPLETED`` non encore
réglés. ``PENDING`` à l'ouverture, puis ``PAID`` (virement accepté par la banque, écriture
``MERCHANT_PAYABLE`` → ``BANK_SETTLEMENT``) ou ``FAILED`` (les paiements restent à régler
au prochain cycle).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from flash.domain.merchants.events import (
    MerchantSettlementFailed,
    MerchantSettlementOpened,
    MerchantSettlementPaid,
)
from flash.domain.shared.errors import InvalidAccountState, InvalidInput
from flash.domain.shared.events import EventRecorder
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import Money


class MerchantSettlementStatus(StrEnum):
    PENDING = "PENDING"
    PAID = "PAID"
    FAILED = "FAILED"


class MerchantSettlement(EventRecorder):
    def __init__(
        self,
        *,
        id: EntityId,
        merchant_id: EntityId,
        user_id: EntityId,
        amount: Money,
        payment_count: int,
        status: MerchantSettlementStatus,
        created_at: datetime,
        currency_code: str | None = None,
        bank_reference: str | None = None,
        failure_reason: str | None = None,
        settled_at: datetime | None = None,
        ledger_transaction_id: EntityId | None = None,
    ) -> None:
        super().__init__()
        if not amount.is_positive:
            raise InvalidInput("Le montant du règlement doit être strictement positif.")
        if payment_count <= 0:
            raise InvalidInput("Un règlement couvre au moins un paiement.")
        self.id = id
        self.merchant_id = merchant_id
        self.user_id = user_id
        self.amount = amount
        self.payment_count = payment_count
        self.status = status
        self.created_at = created_at
        self.currency_code = currency_code or amount.currency.code
        self.bank_reference = bank_reference
        self.failure_reason = failure_reason
        self.settled_at = settled_at
        self.ledger_transaction_id = ledger_transaction_id

    @classmethod
    def open(
        cls,
        *,
        settlement_id: EntityId,
        merchant_id: EntityId,
        user_id: EntityId,
        amount: Money,
        payment_count: int,
        now: datetime,
    ) -> MerchantSettlement:
        settlement = cls(
            id=settlement_id,
            merchant_id=merchant_id,
            user_id=user_id,
            amount=amount,
            payment_count=payment_count,
            status=MerchantSettlementStatus.PENDING,
            created_at=now,
        )
        settlement.record_event(
            MerchantSettlementOpened(
                occurred_at=now,
                aggregate_id=str(settlement_id),
                user_id=str(user_id),
                merchant_id=str(merchant_id),
                amount_minor=amount.amount_minor,
                currency=amount.currency.code,
                payment_count=payment_count,
            )
        )
        return settlement

    @property
    def is_pending(self) -> bool:
        return self.status is MerchantSettlementStatus.PENDING

    def _ensure_pending(self) -> None:
        if not self.is_pending:
            raise InvalidAccountState(
                "Ce règlement est déjà résolu.", status=self.status.value
            )

    def mark_paid(
        self, *, bank_reference: str, ledger_transaction_id: EntityId, now: datetime
    ) -> None:
        self._ensure_pending()
        self.status = MerchantSettlementStatus.PAID
        self.bank_reference = bank_reference
        self.ledger_transaction_id = ledger_transaction_id
        self.settled_at = now
        self.record_event(
            MerchantSettlementPaid(
                occurred_at=now,
                aggregate_id=str(self.id),
                user_id=str(self.user_id),
                merchant_id=str(self.merchant_id),
                amount_minor=self.amount.amount_minor,
                currency=self.currency_code,
                bank_reference=bank_reference,
            )
        )

    def mark_failed(self, *, reason: str, now: datetime) -> None:
        self._ensure_pending()
        self.status = MerchantSettlementStatus.FAILED
        self.failure_reason = reason
        self.settled_at = now
        self.record_event(
            MerchantSettlementFailed(
                occurred_at=now,
                aggregate_id=str(self.id),
                user_id=str(self.user_id),
                merchant_id=str(self.merchant_id),
                amount_minor=self.amount.amount_minor,
                currency=self.currency_code,
                reason=reason,
            )
        )

    def __repr__(self) -> str:
        return (
            f"MerchantSettlement(id={self.id!s}, {self.amount}, "
            f"count={self.payment_count}, status={self.status.value})"
        )


__all__ = ["MerchantSettlement", "MerchantSettlementStatus"]
