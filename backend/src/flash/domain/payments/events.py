"""Événements de l'agrégat PaymentRequest."""

from __future__ import annotations

from dataclasses import dataclass

from flash.domain.shared.events import DomainEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class PaymentRequestCreated(DomainEvent):
    requester_id: str
    payer_id: str
    amount_minor: int
    currency: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PaymentRequestAccepted(DomainEvent):
    requester_id: str
    payer_id: str
    transfer_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PaymentRequestDeclined(DomainEvent):
    requester_id: str
    payer_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PaymentRequestCancelled(DomainEvent):
    requester_id: str
    payer_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PaymentRequestExpired(DomainEvent):
    requester_id: str
    payer_id: str


__all__ = [
    "PaymentRequestAccepted",
    "PaymentRequestCancelled",
    "PaymentRequestCreated",
    "PaymentRequestDeclined",
    "PaymentRequestExpired",
]
