"""Doubles de test pour le sous-système de notifications."""

from __future__ import annotations

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


__all__ = [
    "BoomChannel",
    "InMemoryNotificationRepository",
    "RecordingChannel",
    "RecordingNotifier",
]
