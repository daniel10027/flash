"""Événements de l'agrégat Vault (coffre)."""

from __future__ import annotations

from dataclasses import dataclass

from flash.domain.shared.events import DomainEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class VaultPocketOpened(DomainEvent):
    user_id: str
    wallet_id: str
    pocket_id: str
    pocket_name: str
    goal_minor: int | None
    locked_until: str | None


@dataclass(frozen=True, slots=True, kw_only=True)
class VaultPocketDeposited(DomainEvent):
    user_id: str
    wallet_id: str
    pocket_id: str
    pocket_name: str
    amount_minor: int
    currency: str


@dataclass(frozen=True, slots=True, kw_only=True)
class VaultPocketWithdrawn(DomainEvent):
    user_id: str
    wallet_id: str
    pocket_id: str
    pocket_name: str
    amount_minor: int
    currency: str


@dataclass(frozen=True, slots=True, kw_only=True)
class VaultPocketRenamed(DomainEvent):
    pocket_id: str
    pocket_name: str


@dataclass(frozen=True, slots=True, kw_only=True)
class VaultPocketClosed(DomainEvent):
    user_id: str
    wallet_id: str
    pocket_id: str


__all__ = [
    "VaultPocketClosed",
    "VaultPocketDeposited",
    "VaultPocketOpened",
    "VaultPocketRenamed",
    "VaultPocketWithdrawn",
]
