"""Tests des requêtes notifications : liste, marquage lu (BE-040)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from flash.application.notifications.model import Notification, NotificationKind
from flash.application.notifications.queries import (
    ListNotifications,
    ListNotificationsCommand,
    MarkAllNotificationsRead,
    MarkAllNotificationsReadCommand,
    MarkNotificationRead,
    MarkNotificationReadCommand,
)
from tests.support.notifications import InMemoryNotificationRepository

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _seed(repo: InMemoryNotificationRepository, user_id: str, n: int) -> None:
    for i in range(n):
        repo.add(
            Notification(
                id=f"{user_id}-{i:04d}",
                user_id=user_id,
                kind=NotificationKind.MONEY_IN,
                title=f"n{i}",
                body="b",
                created_at=T0,
            )
        )


@pytest.fixture
def repo() -> InMemoryNotificationRepository:
    return InMemoryNotificationRepository()


class TestListNotifications:
    def test_orders_recent_first_and_paginates(self, repo: InMemoryNotificationRepository) -> None:
        _seed(repo, "u", 5)
        first = ListNotifications(notifications=repo).execute(
            ListNotificationsCommand(user_id="u", limit=2)
        )
        assert [n.title for n in first.items] == ["n4", "n3"]
        assert first.next_cursor == "u-0003"
        assert first.unread_count == 5

        rest = ListNotifications(notifications=repo).execute(
            ListNotificationsCommand(user_id="u", limit=2, cursor=first.next_cursor)
        )
        assert [n.title for n in rest.items] == ["n2", "n1"]
        last = ListNotifications(notifications=repo).execute(
            ListNotificationsCommand(user_id="u", limit=2, cursor=rest.next_cursor)
        )
        assert [n.title for n in last.items] == ["n0"]
        assert last.next_cursor is None

    def test_only_own_notifications(self, repo: InMemoryNotificationRepository) -> None:
        _seed(repo, "u", 2)
        _seed(repo, "other", 3)
        page = ListNotifications(notifications=repo).execute(ListNotificationsCommand(user_id="u"))
        assert len(page.items) == 2

    def test_unread_only_filter(self, repo: InMemoryNotificationRepository) -> None:
        _seed(repo, "u", 3)
        repo.mark_read("u", "u-0001")
        page = ListNotifications(notifications=repo).execute(
            ListNotificationsCommand(user_id="u", unread_only=True)
        )
        assert [n.title for n in page.items] == ["n2", "n0"]
        assert page.unread_count == 2

    def test_limit_is_clamped(self, repo: InMemoryNotificationRepository) -> None:
        _seed(repo, "u", 3)
        page = ListNotifications(notifications=repo).execute(
            ListNotificationsCommand(user_id="u", limit=99999)
        )
        assert len(page.items) == 3 and page.next_cursor is None

    def test_empty(self, repo: InMemoryNotificationRepository) -> None:
        page = ListNotifications(notifications=repo).execute(ListNotificationsCommand(user_id="u"))
        assert page.items == [] and page.unread_count == 0


class TestMarkRead:
    def test_mark_one(self, repo: InMemoryNotificationRepository) -> None:
        _seed(repo, "u", 2)
        assert (
            MarkNotificationRead(notifications=repo).execute(
                MarkNotificationReadCommand(user_id="u", notification_id="u-0000")
            )
            is True
        )
        # rejeu -> déjà lue
        assert (
            MarkNotificationRead(notifications=repo).execute(
                MarkNotificationReadCommand(user_id="u", notification_id="u-0000")
            )
            is False
        )
        assert repo.count_unread("u") == 1

    def test_mark_other_users_notification_is_noop(
        self, repo: InMemoryNotificationRepository
    ) -> None:
        _seed(repo, "other", 1)
        assert (
            MarkNotificationRead(notifications=repo).execute(
                MarkNotificationReadCommand(user_id="u", notification_id="other-0000")
            )
            is False
        )

    def test_mark_all(self, repo: InMemoryNotificationRepository) -> None:
        _seed(repo, "u", 4)
        repo.mark_read("u", "u-0000")
        count = MarkAllNotificationsRead(notifications=repo).execute(
            MarkAllNotificationsReadCommand(user_id="u")
        )
        assert count == 3
        assert repo.count_unread("u") == 0
