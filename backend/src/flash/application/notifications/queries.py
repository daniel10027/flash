"""Lecture et marquage des notifications in-app (BE-040)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flash.application.notifications.model import Notification
from flash.application.notifications.ports import NotificationRepository
from flash.application.use_case import Command, UseCase

_MAX_LIMIT = 100
_DEFAULT_LIMIT = 20


@dataclass(frozen=True, slots=True)
class ListNotificationsCommand(Command):
    user_id: str
    unread_only: bool = False
    limit: int = _DEFAULT_LIMIT
    cursor: str | None = None


@dataclass(frozen=True, slots=True)
class NotificationPage:
    items: list[Notification]
    next_cursor: str | None
    unread_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "items": [n.to_dict() for n in self.items],
            "next_cursor": self.next_cursor,
            "unread_count": self.unread_count,
        }


class ListNotifications(UseCase[ListNotificationsCommand, NotificationPage]):
    def __init__(self, *, notifications: NotificationRepository) -> None:
        self._repo = notifications

    def execute(self, command: ListNotificationsCommand) -> NotificationPage:
        limit = max(1, min(command.limit, _MAX_LIMIT))
        rows = self._repo.list_for_user(
            command.user_id,
            unread_only=command.unread_only,
            limit=limit + 1,
            before=command.cursor,
        )
        has_more = len(rows) > limit
        page = rows[:limit]
        next_cursor = page[-1].id if has_more and page else None
        return NotificationPage(
            items=page,
            next_cursor=next_cursor,
            unread_count=self._repo.count_unread(command.user_id),
        )


@dataclass(frozen=True, slots=True)
class MarkNotificationReadCommand(Command):
    user_id: str
    notification_id: str


class MarkNotificationRead(UseCase[MarkNotificationReadCommand, bool]):
    def __init__(self, *, notifications: NotificationRepository) -> None:
        self._repo = notifications

    def execute(self, command: MarkNotificationReadCommand) -> bool:
        return self._repo.mark_read(command.user_id, command.notification_id)


@dataclass(frozen=True, slots=True)
class MarkAllNotificationsReadCommand(Command):
    user_id: str


class MarkAllNotificationsRead(UseCase[MarkAllNotificationsReadCommand, int]):
    def __init__(self, *, notifications: NotificationRepository) -> None:
        self._repo = notifications

    def execute(self, command: MarkAllNotificationsReadCommand) -> int:
        return self._repo.mark_all_read(command.user_id)


__all__ = [
    "ListNotifications",
    "ListNotificationsCommand",
    "MarkAllNotificationsRead",
    "MarkAllNotificationsReadCommand",
    "MarkNotificationRead",
    "MarkNotificationReadCommand",
    "NotificationPage",
]
