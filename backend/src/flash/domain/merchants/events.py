"""Événements des agrégats marchands."""

from __future__ import annotations

from dataclasses import dataclass

from flash.domain.shared.events import DomainEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class MerchantEnrolled(DomainEvent):
    user_id: str
    currency: str
    fee_bps: int


@dataclass(frozen=True, slots=True, kw_only=True)
class MerchantSuspended(DomainEvent):
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class MerchantChargeOpened(DomainEvent):
    merchant_id: str
    amount_minor: int
    currency: str
    reference: str


@dataclass(frozen=True, slots=True, kw_only=True)
class MerchantChargeCancelled(DomainEvent):
    merchant_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class MerchantChargeExpired(DomainEvent):
    merchant_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class MerchantPaymentCompleted(DomainEvent):
    payer_id: str
    merchant_id: str
    amount_minor: int
    fee_minor: int
    currency: str
    reference: str


@dataclass(frozen=True, slots=True, kw_only=True)
class MerchantPaymentRefunded(DomainEvent):
    payer_id: str
    merchant_id: str
    amount_minor: int
    fee_minor: int
    currency: str
    reference: str
    reversal_transaction_id: str


__all__ = [
    "MerchantChargeCancelled",
    "MerchantChargeExpired",
    "MerchantChargeOpened",
    "MerchantEnrolled",
    "MerchantPaymentCompleted",
    "MerchantPaymentRefunded",
    "MerchantSuspended",
]
