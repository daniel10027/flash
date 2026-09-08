"""Événements de l'agrégat Agent."""

from __future__ import annotations

from dataclasses import dataclass

from flash.domain.shared.events import DomainEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentEnrolled(DomainEvent):
    user_id: str
    currency: str


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentFloatDisbursed(DomainEvent):
    amount_minor: int


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentFloatCollected(DomainEvent):
    amount_minor: int


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentCommissionAccrued(DomainEvent):
    amount_minor: int


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentSuspended(DomainEvent):
    reason: str


__all__ = [
    "AgentCommissionAccrued",
    "AgentEnrolled",
    "AgentFloatCollected",
    "AgentFloatDisbursed",
    "AgentSuspended",
]
