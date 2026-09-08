"""Adapters en mémoire pour les tests de domaine et d'application.

Aucune I/O : tout est déterministe et instantané. Ces fakes respectent les contrats des
ports définis dans ``flash.domain``.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from itertools import count
from typing import Any
from uuid import UUID

from flash.domain.shared.events import DomainEvent
from flash.domain.shared.identifiers import EntityId


class FixedClock:
    """Horloge contrôlée par le test. ``advance`` fait avancer le temps."""

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2026, 1, 1, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, **delta: float) -> None:
        self._now += timedelta(**delta)


class SeqIdGenerator:
    """Génère des UUID déterministes (``00000000-0000-0000-0000-00000000000N``)."""

    def __init__(self) -> None:
        self._counter = count(1)

    def new_id(self) -> EntityId:
        n = next(self._counter)
        return EntityId(UUID(int=n))


class InMemoryIdempotencyStore:
    """Implémente le contrat ``IdempotencyStore`` avec un simple dict."""

    def __init__(self) -> None:
        self._seen: set[str] = set()
        self._results: dict[str, dict[str, Any]] = {}

    def remember(self, key: str, *, ttl_seconds: int) -> bool:
        if key in self._seen:
            return False
        self._seen.add(key)
        return True

    def get_result(self, key: str) -> dict[str, Any] | None:
        return self._results.get(key)

    def save_result(self, key: str, result: dict[str, Any], *, ttl_seconds: int) -> None:
        self._results[key] = result

    def forget(self, key: str) -> None:
        self._seen.discard(key)
        self._results.pop(key, None)


class RecordingEventPublisher:
    """Conserve les événements publiés pour que le test puisse les inspecter."""

    def __init__(self) -> None:
        self.published: list[DomainEvent] = []

    def publish(self, events: list[DomainEvent]) -> None:
        self.published.extend(events)

    def names(self) -> list[str]:
        return [e.name for e in self.published]


class FakePinHasher:
    """Hachage réversible et déterministe — pour les tests uniquement."""

    _PREFIX = "hashed:"

    def hash(self, pin: object) -> str:
        return f"{self._PREFIX}{getattr(pin, 'value', pin)}"

    def verify(self, pin: object, hashed: str) -> bool:
        return hashed == self.hash(pin)

    def needs_rehash(self, hashed: str) -> bool:
        return not hashed.startswith(self._PREFIX)


__all__ = [
    "FakePinHasher",
    "FixedClock",
    "InMemoryIdempotencyStore",
    "RecordingEventPublisher",
    "SeqIdGenerator",
]
