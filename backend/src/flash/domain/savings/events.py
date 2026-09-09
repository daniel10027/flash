"""Événements de l'agrégat ``SavingsPlan``."""

from __future__ import annotations

from dataclasses import dataclass

from flash.domain.shared.events import DomainEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class SavingsPlanOpened(DomainEvent):
    user_id: str
    wallet_id: str
    plan_id: str
    plan_name: str
    annual_rate_bps: int
    frequency: str
    contribution_minor: int
    target_minor: int | None
    target_date: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class SavingsPlanFunded(DomainEvent):
    user_id: str
    wallet_id: str
    plan_id: str
    plan_name: str
    amount_minor: int
    currency: str
    scheduled: bool


@dataclass(frozen=True, slots=True, kw_only=True)
class SavingsPlanWithdrawn(DomainEvent):
    user_id: str
    wallet_id: str
    plan_id: str
    plan_name: str
    amount_minor: int
    currency: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SavingsContributionSkipped(DomainEvent):
    user_id: str
    wallet_id: str
    plan_id: str
    plan_name: str
    amount_minor: int
    currency: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SavingsInterestAccrued(DomainEvent):
    plan_id: str
    accrued_total_micro: int


@dataclass(frozen=True, slots=True, kw_only=True)
class SavingsInterestCapitalised(DomainEvent):
    user_id: str
    wallet_id: str
    plan_id: str
    plan_name: str
    amount_minor: int
    currency: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SavingsPlanClosed(DomainEvent):
    user_id: str
    wallet_id: str
    plan_id: str
    plan_name: str
    amount_minor: int
    currency: str


__all__ = [
    "SavingsContributionSkipped",
    "SavingsInterestAccrued",
    "SavingsInterestCapitalised",
    "SavingsPlanClosed",
    "SavingsPlanFunded",
    "SavingsPlanOpened",
    "SavingsPlanWithdrawn",
]
