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
class AgentCommissionPaid(DomainEvent):
    amount_minor: int


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentAttachedToMaster(DomainEvent):
    master_agent_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentFloatToppedUp(DomainEvent):
    amount_minor: int
    float_after_minor: int


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentFloatWithdrawn(DomainEvent):
    amount_minor: int
    float_after_minor: int


@dataclass(frozen=True, slots=True, kw_only=True)
class AgentSuspended(DomainEvent):
    reason: str


__all__ = [
    "AgentAttachedToMaster",
    "AgentCommissionAccrued",
    "AgentCommissionPaid",
    "AgentEnrolled",
    "AgentFloatCollected",
    "AgentFloatDisbursed",
    "AgentFloatToppedUp",
    "AgentFloatWithdrawn",
    "AgentSuspended",
]
