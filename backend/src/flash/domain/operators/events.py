"""Événements de l'agrégat ``OperatorTransfer`` (payout / collect)."""

from __future__ import annotations

from dataclasses import dataclass

from flash.domain.shared.events import DomainEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class OperatorTransferInitiated(DomainEvent):
    user_id: str
    wallet_id: str
    operator: str
    direction: str
    msisdn_masked: str
    amount_minor: int
    currency: str
    reference: str


@dataclass(frozen=True, slots=True, kw_only=True)
class OperatorTransferSucceeded(DomainEvent):
    user_id: str
    wallet_id: str
    operator: str
    direction: str
    msisdn_masked: str
    amount_minor: int
    fee_minor: int
    currency: str
    reference: str


@dataclass(frozen=True, slots=True, kw_only=True)
class OperatorTransferFailed(DomainEvent):
    user_id: str
    wallet_id: str
    operator: str
    direction: str
    amount_minor: int
    currency: str
    reference: str
    reason: str


__all__ = [
    "OperatorTransferFailed",
    "OperatorTransferInitiated",
    "OperatorTransferSucceeded",
]
