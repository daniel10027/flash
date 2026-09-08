"""Agrégat ``Merchant`` — un commerçant qui encaisse des paiements par QR.

Le paiement marchand est **gratuit pour le client** (modèle Wave) ; le marchand paie une
commission ``fee_bps`` prélevée sur le montant encaissé. Le net va sur un compte
``MERCHANT_PAYABLE`` (dette de Flash envers le marchand), soldé plus tard par un
règlement (``BE-063``, hors périmètre BE-033).
"""

from __future__ import annotations

from datetime import datetime
from decimal import ROUND_FLOOR
from enum import StrEnum

from flash.domain.merchants.events import MerchantEnrolled, MerchantSuspended
from flash.domain.shared.errors import InvalidAccountState
from flash.domain.shared.events import EventRecorder
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import Currency, Money

_MAX_FEE_BPS = 1_000  # 10 %


class MerchantStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class Merchant(EventRecorder):
    def __init__(
        self,
        *,
        id: EntityId,
        user_id: EntityId,
        display_name: str,
        category: str,
        currency: Currency,
        fee_bps: int,
        created_at: datetime,
        status: MerchantStatus = MerchantStatus.ACTIVE,
    ) -> None:
        super().__init__()
        if not display_name.strip():
            raise ValueError("Le nom commercial est requis.")
        if not 0 <= fee_bps <= _MAX_FEE_BPS:
            raise ValueError("fee_bps hors bornes (0 à 1000).")
        self.id = id
        self.user_id = user_id
        self.display_name = display_name.strip()
        self.category = category.strip() or "GENERAL"
        self.currency = currency
        self.fee_bps = fee_bps
        self.created_at = created_at
        self.status = status

    @classmethod
    def enroll(
        cls,
        *,
        merchant_id: EntityId,
        user_id: EntityId,
        display_name: str,
        category: str,
        currency: Currency,
        fee_bps: int,
        now: datetime,
    ) -> Merchant:
        merchant = cls(
            id=merchant_id,
            user_id=user_id,
            display_name=display_name,
            category=category,
            currency=currency,
            fee_bps=fee_bps,
            created_at=now,
        )
        merchant.record_event(
            MerchantEnrolled(
                occurred_at=now,
                aggregate_id=str(merchant_id),
                user_id=str(user_id),
                currency=currency.code,
                fee_bps=fee_bps,
            )
        )
        return merchant

    def ensure_active(self) -> None:
        if self.status is not MerchantStatus.ACTIVE:
            raise InvalidAccountState("Ce marchand est suspendu.", status=self.status.value)

    def fee_for(self, amount: Money) -> Money:
        if amount.currency != self.currency:
            raise ValueError("Devise du montant différente de celle du marchand.")
        return amount.percentage(self.fee_bps, rounding=ROUND_FLOOR)

    def suspend(self, reason: str, now: datetime) -> None:
        if self.status is MerchantStatus.SUSPENDED:
            return
        self.status = MerchantStatus.SUSPENDED
        self.record_event(
            MerchantSuspended(occurred_at=now, aggregate_id=str(self.id), reason=reason)
        )

    def static_qr_payload(self) -> str:
        """QR statique : identifie le marchand, le montant est saisi par le client."""
        return f"flash://pay?m={self.id}"

    def __repr__(self) -> str:
        return f"Merchant(id={self.id!s}, name={self.display_name!r}, fee_bps={self.fee_bps})"


__all__ = ["Merchant", "MerchantStatus"]
