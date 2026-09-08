"""Événements de domaine.

Un agrégat enregistre ses événements via ``record_event`` ; la couche application les
collecte après un cas d'usage réussi et les publie (pattern *outbox*). Les événements
sont des faits passés, immuables, nommés au participe passé.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True, kw_only=True)
class DomainEvent:
    """Fait métier survenu. Les sous-classes ajoutent leurs données propres."""

    occurred_at: datetime
    aggregate_id: str

    @property
    def name(self) -> str:
        return type(self).__name__

    def to_payload(self) -> dict[str, Any]:
        """Représentation sérialisable (pour l'outbox et les notifications)."""
        out: dict[str, Any] = {}
        for key in self.__dataclass_fields__:
            value = getattr(self, key)
            out[key] = value.isoformat() if isinstance(value, datetime) else value
        return out


class EventRecorder:
    """Mixin pour les racines d'agrégat : accumule les événements en attente."""

    _pending_events: list[DomainEvent]

    def __init__(self) -> None:
        self._pending_events = []

    def record_event(self, event: DomainEvent) -> None:
        self._pending_events.append(event)

    def pull_events(self) -> list[DomainEvent]:
        """Retourne et vide la file d'événements de l'agrégat."""
        events = list(self._pending_events)
        self._pending_events.clear()
        return events


__all__ = ["DomainEvent", "EventRecorder"]
