"""Événements des ordres cash (dépôt / retrait en agence)."""

from __future__ import annotations

from dataclasses import dataclass

from flash.domain.shared.events import DomainEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class CashDepositCompleted(DomainEvent):
    client_id: str
    agent_id: str
    amount_minor: int
    currency: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CashWithdrawalInitiated(DomainEvent):
    client_id: str
    amount_minor: int
    fee_minor: int
    currency: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CashWithdrawalConfirmed(DomainEvent):
    client_id: str
    agent_id: str
    amount_minor: int
    fee_minor: int
    currency: str


@dataclass(frozen=True, slots=True, kw_only=True)
class CashWithdrawalCancelled(DomainEvent):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class CashWithdrawalExpired(DomainEvent):
    pass


__all__ = [
    "CashDepositCompleted",
    "CashWithdrawalCancelled",
    "CashWithdrawalConfirmed",
    "CashWithdrawalExpired",
    "CashWithdrawalInitiated",
]
