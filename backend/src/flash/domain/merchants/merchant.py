"""Agrégat ``Merchant`` — un commerçant qui encaisse des paiements par QR.

Le paiement marchand est **gratuit pour le client** (modèle Wave) ; le marchand paie une
commission ``fee_bps`` prélevée sur le montant encaissé. Le net va sur un compte
``MERCHANT_PAYABLE`` (dette de Flash envers le marchand), soldé périodiquement par un
**règlement** (``BE-070``) : virement du net accumulé vers le compte bancaire du
marchand (``MERCHANT_PAYABLE`` → ``BANK_SETTLEMENT``).
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timedelta
from decimal import ROUND_FLOOR
from enum import StrEnum

from flash.domain.merchants.bank_account import BankAccount
from flash.domain.merchants.events import (
    MerchantChannelFeeChanged,
    MerchantEnrolled,
    MerchantKybApproved,
    MerchantKybRejected,
    MerchantKybSubmitted,
    MerchantSettlementConfigured,
    MerchantSuspended,
    MerchantWebhookConfigured,
)
from flash.domain.shared.errors import InvalidAccountState, InvalidInput
from flash.domain.shared.events import EventRecorder
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import Currency, Money

_MAX_FEE_BPS = 1_000  # 10 %


class MerchantStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class PaymentChannel(StrEnum):
    """Canal d'encaissement — sert aux **frais négociés par canal** (reste de BE-068)."""

    QR = "QR"  # QR statique / dynamique, encaissement en présentiel
    API = "API"  # API marchande publique ``/merchant/v1`` (e-commerce, à distance)


class KybStatus(StrEnum):
    """*Know Your Business* : état de la vérification du marchand."""

    PENDING = "PENDING"
    APPROVED = "APPROVED"
    REJECTED = "REJECTED"


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
        kyb_status: KybStatus = KybStatus.PENDING,
        kyb_reviewed_at: datetime | None = None,
        kyb_reason: str | None = None,
        webhook_url: str | None = None,
        webhook_secret: str | None = None,
        channel_fees: Mapping[str, int] | None = None,
    ) -> None:
        super().__init__()
        if not display_name.strip():
            raise ValueError("Le nom commercial est requis.")
        if not 0 <= fee_bps <= _MAX_FEE_BPS:
            raise ValueError("fee_bps hors bornes (0 à 1000).")
        self.channel_fees: dict[str, int] = {}
        for raw_channel, bps in (channel_fees or {}).items():
            channel = PaymentChannel(raw_channel)
            if not 0 <= bps <= _MAX_FEE_BPS:
                raise ValueError("fee_bps négocié hors bornes (0 à 1000).")
            self.channel_fees[channel.value] = bps
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
        self.kyb_status = kyb_status
        self.kyb_reviewed_at = kyb_reviewed_at
        self.kyb_reason = kyb_reason
        self.webhook_url = webhook_url
        self.webhook_secret = webhook_secret

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

    def effective_fee_bps(self, channel: PaymentChannel = PaymentChannel.QR) -> int:
        """Commission applicable : override négocié du canal, sinon ``fee_bps``."""
        return self.channel_fees.get(channel.value, self.fee_bps)

    def fee_for(
        self, amount: Money, *, channel: PaymentChannel = PaymentChannel.QR
    ) -> Money:
        if amount.currency != self.currency:
            raise ValueError("Devise du montant différente de celle du marchand.")
        return amount.percentage(
            self.effective_fee_bps(channel), rounding=ROUND_FLOOR
        )

    def set_channel_fee(
        self, *, channel: PaymentChannel, fee_bps: int, now: datetime
    ) -> None:
        """Fixe une commission négociée pour un canal (back-office)."""
        if not 0 <= fee_bps <= _MAX_FEE_BPS:
            raise InvalidInput("fee_bps négocié hors bornes (0 à 1000).")
        self.channel_fees[channel.value] = fee_bps
        self.record_event(
            MerchantChannelFeeChanged(
                occurred_at=now,
                aggregate_id=str(self.id),
                merchant_id=str(self.id),
                channel=channel.value,
                fee_bps=fee_bps,
            )
        )

    def clear_channel_fee(self, *, channel: PaymentChannel, now: datetime) -> None:
        """Retire l'override d'un canal : retour au ``fee_bps`` par défaut."""
        if self.channel_fees.pop(channel.value, None) is None:
            raise InvalidInput("Aucune commission négociée pour ce canal.")
        self.record_event(
            MerchantChannelFeeChanged(
                occurred_at=now,
                aggregate_id=str(self.id),
                merchant_id=str(self.id),
                channel=channel.value,
                fee_bps=None,
            )
        )

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

    # ------------------------------------------------------------------ KYB
    def submit_kyb(self, now: datetime) -> None:
        """Le marchand soumet (ou re-soumet) son dossier de vérification."""
        if self.kyb_status is KybStatus.APPROVED:
            raise InvalidAccountState("Ce marchand est déjà vérifié.", status="APPROVED")
        self.kyb_status = KybStatus.PENDING
        self.kyb_reason = None
        self.record_event(
            MerchantKybSubmitted(
                occurred_at=now, aggregate_id=str(self.id), user_id=str(self.user_id)
            )
        )

    def approve_kyb(self, *, reviewer: str, now: datetime) -> None:
        if self.kyb_status is KybStatus.APPROVED:
            return
        self.kyb_status = KybStatus.APPROVED
        self.kyb_reviewed_at = now
        self.kyb_reason = None
        self.record_event(
            MerchantKybApproved(
                occurred_at=now,
                aggregate_id=str(self.id),
                user_id=str(self.user_id),
                reviewer=reviewer,
            )
        )

    def reject_kyb(self, *, reviewer: str, reason: str, now: datetime) -> None:
        if not reason.strip():
            raise InvalidInput("Un motif de rejet est requis.")
        self.kyb_status = KybStatus.REJECTED
        self.kyb_reviewed_at = now
        self.kyb_reason = reason.strip()
        self.record_event(
            MerchantKybRejected(
                occurred_at=now,
                aggregate_id=str(self.id),
                user_id=str(self.user_id),
                reviewer=reviewer,
                reason=reason.strip(),
            )
        )

    @property
    def kyb_approved(self) -> bool:
        return self.kyb_status is KybStatus.APPROVED

    def ensure_kyb_approved(self) -> None:
        if self.kyb_status is not KybStatus.APPROVED:
            raise InvalidAccountState(
                "La vérification du marchand (KYB) n'est pas validée.",
                status=self.kyb_status.value,
            )

    # ------------------------------------------------------------------ webhooks
    def configure_webhook(self, *, url: str, secret: str, now: datetime) -> None:
        cleaned = url.strip()
        if not cleaned.startswith(("http://", "https://")):
            raise InvalidInput("L'URL de webhook doit être en http(s).")
        if len(secret) < 16:
            raise InvalidInput("Le secret de webhook doit faire au moins 16 caractères.")
        self.webhook_url = cleaned
        self.webhook_secret = secret
        self.record_event(
            MerchantWebhookConfigured(
                occurred_at=now, aggregate_id=str(self.id), merchant_id=str(self.id),
                endpoint=cleaned,
            )
        )

    def clear_webhook(self, now: datetime) -> None:
        self.webhook_url = None
        self.webhook_secret = None
        self.record_event(
            MerchantWebhookConfigured(
                occurred_at=now, aggregate_id=str(self.id), merchant_id=str(self.id),
                endpoint="",
            )
        )

    @property
    def has_webhook(self) -> bool:
        return bool(self.webhook_url and self.webhook_secret)

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


__all__ = [
    "KybStatus",
    "Merchant",
    "MerchantStatus",
    "PaymentChannel",
    "SettlementFrequency",
]
