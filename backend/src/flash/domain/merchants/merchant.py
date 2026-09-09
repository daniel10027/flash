"""Agrégat ``Merchant`` — un commerçant qui encaisse des paiements par QR.

Le paiement marchand est **gratuit pour le client** (modèle Wave) ; le marchand paie une
commission ``fee_bps`` prélevée sur le montant encaissé. Le net va sur un compte
``MERCHANT_PAYABLE`` (dette de Flash envers le marchand), soldé périodiquement par un
**règlement** (``BE-070``) : virement du net accumulé vers le compte bancaire du
marchand (``MERCHANT_PAYABLE`` → ``BANK_SETTLEMENT``).
"""

from __future__ import annotations

from datetime import datetime, timedelta
from decimal import ROUND_FLOOR
from enum import StrEnum

from flash.domain.merchants.bank_account import BankAccount
from flash.domain.merchants.events import (
    MerchantEnrolled,
    MerchantSettlementConfigured,
    MerchantSuspended,
)
from flash.domain.shared.errors import InvalidAccountState, InvalidInput
from flash.domain.shared.events import EventRecorder
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import Currency, Money

_MAX_FEE_BPS = 1_000  # 10 %


class MerchantStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class SettlementFrequency(StrEnum):
    MANUAL = "MANUAL"
    DAILY = "DAILY"
    WEEKLY = "WEEKLY"
    MONTHLY = "MONTHLY"

    @property
    def period(self) -> timedelta | None:
        return {
            SettlementFrequency.DAILY: timedelta(days=1),
            SettlementFrequency.WEEKLY: timedelta(days=7),
            SettlementFrequency.MONTHLY: timedelta(days=30),
        }.get(self)


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
        settlement_frequency: SettlementFrequency = SettlementFrequency.MANUAL,
        bank_account: BankAccount | None = None,
        next_settlement_at: datetime | None = None,
        last_settlement_id: EntityId | None = None,
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
        self.settlement_frequency = settlement_frequency
        self.bank_account = bank_account
        self.next_settlement_at = next_settlement_at
        self.last_settlement_id = last_settlement_id

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

    # ------------------------------------------------------------------ règlement
    def configure_settlement(
        self, *, bank_account: BankAccount, frequency: SettlementFrequency, now: datetime
    ) -> None:
        self.bank_account = bank_account
        self.settlement_frequency = frequency
        period = frequency.period
        self.next_settlement_at = (now + period) if period is not None else None
        self.record_event(
            MerchantSettlementConfigured(
                occurred_at=now,
                aggregate_id=str(self.id),
                user_id=str(self.user_id),
                merchant_id=str(self.id),
                frequency=frequency.value,
                bank_iban_masked=bank_account.masked(),
            )
        )

    @property
    def can_settle(self) -> bool:
        return self.status is MerchantStatus.ACTIVE and self.bank_account is not None

    def require_bank_account(self) -> BankAccount:
        if self.bank_account is None:
            raise InvalidInput("Aucun compte bancaire de règlement configuré.")
        return self.bank_account

    def due_for_settlement(self, now: datetime) -> bool:
        return (
            self.can_settle
            and self.settlement_frequency.period is not None
            and self.next_settlement_at is not None
            and now >= self.next_settlement_at
        )

    def advance_settlement_schedule(self, now: datetime) -> None:
        period = self.settlement_frequency.period
        if period is None or self.next_settlement_at is None:
            return
        nxt = self.next_settlement_at
        while nxt <= now:
            nxt = nxt + period
        self.next_settlement_at = nxt

    def record_settlement(self, *, settlement_id: EntityId, now: datetime) -> None:
        self.last_settlement_id = settlement_id
        self.advance_settlement_schedule(now)

    def __repr__(self) -> str:
        return f"Merchant(id={self.id!s}, name={self.display_name!r}, fee_bps={self.fee_bps})"


__all__ = ["Merchant", "MerchantStatus", "SettlementFrequency"]
