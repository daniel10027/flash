"""Événements de l'agrégat Wallet."""

from __future__ import annotations

from dataclasses import dataclass

from flash.domain.shared.events import DomainEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class WalletOpened(DomainEvent):
    user_id: str
    currency: str


@dataclass(frozen=True, slots=True, kw_only=True)
class WalletCredited(DomainEvent):
    amount_minor: int
    currency: str


@dataclass(frozen=True, slots=True, kw_only=True)
class WalletDebited(DomainEvent):
    amount_minor: int
    currency: str


@dataclass(frozen=True, slots=True, kw_only=True)
class FundsReserved(DomainEvent):
    amount_minor: int
    currency: str


@dataclass(frozen=True, slots=True, kw_only=True)
class FundsReleased(DomainEvent):
    amount_minor: int
    currency: str


@dataclass(frozen=True, slots=True, kw_only=True)
class ReservationSettled(DomainEvent):
    amount_minor: int
    currency: str


@dataclass(frozen=True, slots=True, kw_only=True)
class WalletFrozen(DomainEvent):
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class WalletUnfrozen(DomainEvent):
    pass


__all__ = [
    "FundsReleased",
    "FundsReserved",
    "ReservationSettled",
    "WalletCredited",
    "WalletDebited",
    "WalletFrozen",
    "WalletOpened",
    "WalletUnfrozen",
]
