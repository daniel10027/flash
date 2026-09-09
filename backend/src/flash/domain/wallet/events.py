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
class FundsVaulted(DomainEvent):
    """Des fonds ont quitté le disponible pour une poche de coffre."""

    amount_minor: int
    currency: str


@dataclass(frozen=True, slots=True, kw_only=True)
class FundsUnvaulted(DomainEvent):
    """Des fonds sont revenus d'une poche de coffre au disponible."""

    amount_minor: int
    currency: str


@dataclass(frozen=True, slots=True, kw_only=True)
class FundsSaved(DomainEvent):
    """Des fonds ont quitté le disponible pour un plan d'épargne."""

    amount_minor: int
    currency: str


@dataclass(frozen=True, slots=True, kw_only=True)
class FundsUnsaved(DomainEvent):
    """Des fonds sont revenus d'un plan d'épargne au disponible."""

    amount_minor: int
    currency: str


@dataclass(frozen=True, slots=True, kw_only=True)
class SavingsInterestCredited(DomainEvent):
    """Des intérêts d'épargne ont été capitalisés (nouvelle valeur, hors disponible)."""

    amount_minor: int
    currency: str


@dataclass(frozen=True, slots=True, kw_only=True)
class WalletFrozen(DomainEvent):
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class WalletUnfrozen(DomainEvent):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class TransferCompleted(DomainEvent):
    """Un transfert P2P a été exécuté. ``aggregate_id`` = id de la LedgerTransaction."""

    sender_id: str
    recipient_id: str
    amount_minor: int
    fee_minor: int
    currency: str
    reference: str


@dataclass(frozen=True, slots=True, kw_only=True)
class TransferReversed(DomainEvent):
    """Un transfert P2P a été annulé (contre-passation). ``aggregate_id`` = id du
    ``REVERSAL``."""

    original_transfer_id: str
    sender_id: str
    recipient_id: str
    amount_minor: int
    fee_minor: int
    currency: str
    reference: str


__all__ = [
    "FundsReleased",
    "FundsReserved",
    "FundsSaved",
    "FundsUnsaved",
    "FundsUnvaulted",
    "FundsVaulted",
    "ReservationSettled",
    "SavingsInterestCredited",
    "TransferCompleted",
    "TransferReversed",
    "WalletCredited",
    "WalletDebited",
    "WalletFrozen",
    "WalletOpened",
    "WalletUnfrozen",
]
