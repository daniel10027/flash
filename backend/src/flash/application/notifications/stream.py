"""Flux temps réel des notifications d'un utilisateur (BE-042).

Compose : rattrapage des notifications manquées (``Last-Event-ID``) puis abonnement au
bus temps réel. Le formatage SSE reste dans la couche interface ; ici on ne produit que
des ``Notification`` (ou ``None`` = occasion de keep-alive).
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass

from flash.application.notifications.model import Notification
from flash.application.notifications.ports import NotificationBus, NotificationRepository

_BACKLOG_LIMIT = 100


@dataclass(frozen=True, slots=True)
class StreamNotificationsCommand:
    user_id: str
    last_event_id: str | None = None


class NotificationStream:
    def __init__(self, *, notifications: NotificationRepository, bus: NotificationBus) -> None:
        self._repo = notifications
        self._bus = bus

    def events(self, command: StreamNotificationsCommand) -> Iterator[Notification | None]:
        seen: set[str] = set()
        if command.last_event_id:
            for missed in self._repo.list_since(
                command.user_id, command.last_event_id, limit=_BACKLOG_LIMIT
            ):
                seen.add(missed.id)
                yield missed
        for item in self._bus.subscribe(command.user_id):
            if item is None:
                yield None
                continue
            if item.id in seen:  # déjà rattrapé
                continue
            seen.add(item.id)
            yield item


__all__ = ["NotificationStream", "StreamNotificationsCommand"]
