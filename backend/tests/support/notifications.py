"""Doubles de test pour le sous-système de notifications."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterator
from datetime import UTC, datetime

from flash.application.notifications.model import Notification
from flash.application.notifications.ports import NotificationChannel


class RecordingNotifier:
    """``Notifier`` de test : conserve tout ce qui est livré."""

    def __init__(self) -> None:
        self.delivered: list[Notification] = []

    def deliver(self, notification: Notification) -> None:
        self.delivered.append(notification)

    def for_user(self, user_id: str) -> list[Notification]:
        return [n for n in self.delivered if n.user_id == user_id]


class RecordingChannel(NotificationChannel):
    def __init__(self) -> None:
        self.sent: list[Notification] = []

    def send(self, notification: Notification) -> None:
        self.sent.append(notification)


class BoomChannel(NotificationChannel):
    def send(self, notification: Notification) -> None:
        raise RuntimeError("canal en panne")


class InMemoryNotificationRepository:
    def __init__(self) -> None:
        self._by_id: dict[str, Notification] = {}

    def add(self, notification: Notification) -> None:
        self._by_id[notification.id] = notification

    def get(self, notification_id: str) -> Notification | None:
        return self._by_id.get(notification_id)

    def list_for_user(
        self,
        user_id: str,
        *,
        unread_only: bool = False,
        limit: int = 20,
        before: str | None = None,
    ) -> list[Notification]:
        rows = [n for n in self._by_id.values() if n.user_id == user_id]
        if unread_only:
            rows = [n for n in rows if not n.is_read]
        rows.sort(key=lambda n: n.id, reverse=True)
        if before:
            rows = [n for n in rows if n.id < before]
        return rows[:limit]

    def list_since(self, user_id: str, after_id: str, *, limit: int = 100) -> list[Notification]:
        rows = [n for n in self._by_id.values() if n.user_id == user_id and n.id > after_id]
        rows.sort(key=lambda n: n.id)
        return rows[:limit]

    def count_unread(self, user_id: str) -> int:
        return sum(1 for n in self._by_id.values() if n.user_id == user_id and not n.is_read)

    def mark_read(self, user_id: str, notification_id: str) -> bool:
        n = self._by_id.get(notification_id)
        if n is None or n.user_id != user_id or n.is_read:
            return False
        self._by_id[notification_id] = Notification(
            id=n.id,
            user_id=n.user_id,
            kind=n.kind,
            title=n.title,
            body=n.body,
            created_at=n.created_at,
            data=n.data,
            read_at=datetime.now(UTC),
        )
        return True

    def mark_all_read(self, user_id: str) -> int:
        count = 0
        for nid, n in list(self._by_id.items()):
            if n.user_id == user_id and not n.is_read:
                self.mark_read(user_id, nid)
                count += 1
        return count


class InMemoryNotificationBus:
    """Bus de test façon pub/sub : un ``publish`` est perdu si personne n'écoute.

    ``subscribe`` s'enregistre, livre ce qui est publié tant qu'il itère, puis émet un
    ``None`` (keep-alive) et se termine — flux borné pour les tests. ``prime`` permet à
    un test de mettre des notifications « en vol » juste avant l'abonnement.
    """

    def __init__(self) -> None:
        self._primed: dict[str, list[Notification]] = defaultdict(list)
        self._listeners: set[str] = set()

    def prime(self, notification: Notification) -> None:
        self._primed[notification.user_id].append(notification)

    def publish(self, notification: Notification) -> None:
        if notification.user_id in self._listeners:
            self._primed[notification.user_id].append(notification)

    def subscribe(self, user_id: str) -> Iterator[Notification | None]:
        self._listeners.add(user_id)
        try:
            queue = self._primed[user_id]
            while queue:
                yield queue.pop(0)
            yield None  # keep-alive puis fin (test borné)
        finally:
            self._listeners.discard(user_id)


__all__ = [
    "BoomChannel",
    "InMemoryNotificationBus",
    "InMemoryNotificationRepository",
    "RecordingChannel",
    "RecordingNotifier",
]
