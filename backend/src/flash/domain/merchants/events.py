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


@dataclass(frozen=True, slots=True, kw_only=True)
class MerchantSettlementConfigured(DomainEvent):
    user_id: str
    merchant_id: str
    frequency: str
    bank_iban_masked: str


@dataclass(frozen=True, slots=True, kw_only=True)
class MerchantSettlementOpened(DomainEvent):
    user_id: str
    merchant_id: str
    amount_minor: int
    currency: str
    payment_count: int


@dataclass(frozen=True, slots=True, kw_only=True)
class MerchantSettlementPaid(DomainEvent):
    user_id: str
    merchant_id: str
    amount_minor: int
    currency: str
    bank_reference: str


@dataclass(frozen=True, slots=True, kw_only=True)
class MerchantSettlementFailed(DomainEvent):
    user_id: str
    merchant_id: str
    amount_minor: int
    currency: str
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class MerchantKybSubmitted(DomainEvent):
    user_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class MerchantKybApproved(DomainEvent):
    user_id: str
    reviewer: str


@dataclass(frozen=True, slots=True, kw_only=True)
class MerchantKybRejected(DomainEvent):
    user_id: str
    reviewer: str
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class MerchantApiKeyIssued(DomainEvent):
    merchant_id: str
    key_prefix: str
    label: str


@dataclass(frozen=True, slots=True, kw_only=True)
class MerchantApiKeyRevoked(DomainEvent):
    merchant_id: str
    key_prefix: str


__all__ = [
    "MerchantApiKeyIssued",
    "MerchantApiKeyRevoked",
    "MerchantChargeCancelled",
    "MerchantChargeExpired",
    "MerchantChargeOpened",
    "MerchantEnrolled",
    "MerchantKybApproved",
    "MerchantKybRejected",
    "MerchantKybSubmitted",
    "MerchantPaymentCompleted",
    "MerchantPaymentRefunded",
    "MerchantSettlementConfigured",
    "MerchantSettlementFailed",
    "MerchantSettlementOpened",
    "MerchantSettlementPaid",
    "MerchantSuspended",
]
