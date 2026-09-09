"""Événements des agrégats carte (``Card`` et ``CardAuthorization``)."""

from __future__ import annotations

from dataclasses import dataclass

from flash.domain.shared.events import DomainEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class CardIssued(DomainEvent):
    user_id: str
    wallet_id: str
    card_id: str
    network: str
    last4: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CardFrozen(DomainEvent):
    user_id: str
    card_id: str
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CardUnfrozen(DomainEvent):
    user_id: str
    card_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CardClosed(DomainEvent):
    user_id: str
    card_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CardLimitsChanged(DomainEvent):
    user_id: str
    card_id: str
    daily_limit_minor: int
    monthly_limit_minor: int


@dataclass(frozen=True, slots=True, kw_only=True)
class CardSensitiveViewed(DomainEvent):
    """Audit : les données sensibles (PAN/CVV) ont été révélées à l'utilisateur."""

    user_id: str
    card_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CardPaymentAuthorized(DomainEvent):
    user_id: str
    wallet_id: str
    card_id: str
    authorization_id: str
    amount_minor: int
    currency: str
    channel: str
    merchant_name: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class CardPaymentDeclined(DomainEvent):
    user_id: str
    card_id: str
    authorization_id: str
    amount_minor: int
    currency: str
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CardPaymentCaptured(DomainEvent):
    user_id: str
    wallet_id: str
    card_id: str
    authorization_id: str
    amount_minor: int
    currency: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CardAuthorizationReversed(DomainEvent):
    user_id: str
    wallet_id: str
    card_id: str
    authorization_id: str
    amount_minor: int
    currency: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CardPaymentRefunded(DomainEvent):
    user_id: str
    wallet_id: str
    card_id: str
    authorization_id: str
    amount_minor: int
    currency: str


__all__ = [
    "CardAuthorizationReversed",
    "CardClosed",
    "CardFrozen",
    "CardIssued",
    "CardLimitsChanged",
    "CardPaymentAuthorized",
    "CardPaymentCaptured",
    "CardPaymentDeclined",
    "CardPaymentRefunded",
    "CardSensitiveViewed",
    "CardUnfrozen",
]
