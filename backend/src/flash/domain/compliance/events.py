"""Événements du sous-domaine conformité (BE-076)."""

from __future__ import annotations

from dataclasses import dataclass

from flash.domain.shared.events import DomainEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class ComplianceAlertOpened(DomainEvent):
    user_id: str
    kind: str
    score: int


@dataclass(frozen=True, slots=True, kw_only=True)
class ComplianceAlertResolved(DomainEvent):
    user_id: str
    outcome: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ComplianceAlertEscalated(DomainEvent):
    user_id: str
    note: str


__all__ = [
    "ComplianceAlertEscalated",
    "ComplianceAlertOpened",
    "ComplianceAlertResolved",
]
