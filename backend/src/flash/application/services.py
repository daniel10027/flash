"""Regroupement des dépendances transverses injectées dans les cas d'usage."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass

from flash.application.unit_of_work import WorkUnitOfWork
from flash.domain.shared.ports import (
    Clock,
    EventPublisher,
    IdempotencyStore,
    IdGenerator,
)

UnitOfWorkFactory = Callable[[], WorkUnitOfWork]


@dataclass(frozen=True, slots=True)
class AppServices:
    """Boîte à outils commune à tous les cas d'usage.

    Fournie une fois au démarrage (câblage dans ``interface``) et passée aux cas
    d'usage à la construction.
    """

    uow: UnitOfWorkFactory
    clock: Clock
    ids: IdGenerator
    events: EventPublisher
    idempotency: IdempotencyStore


__all__ = ["AppServices", "UnitOfWorkFactory"]
