"""Tests de NotificationStream : rattrapage + flux live (BE-042)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from flash.application.notifications.model import Notification, NotificationKind
from flash.application.notifications.stream import NotificationStream, StreamNotificationsCommand
from tests.support.notifications import InMemoryNotificationBus, InMemoryNotificationRepository

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _note(nid: str, user: str = "u") -> Notification:
    return Notification(
        id=nid,
        user_id=user,
        kind=NotificationKind.MONEY_IN,
        title=nid,
        body="b",
        created_at=T0,
    )


@pytest.fixture
def repo() -> InMemoryNotificationRepository:
    return InMemoryNotificationRepository()


@pytest.fixture
def bus() -> InMemoryNotificationBus:
    return InMemoryNotificationBus()


@pytest.fixture
def stream(
    repo: InMemoryNotificationRepository, bus: InMemoryNotificationBus
) -> NotificationStream:
    return NotificationStream(notifications=repo, bus=bus)


def test_without_last_event_id_only_live(
    stream: NotificationStream, repo: InMemoryNotificationRepository, bus: InMemoryNotificationBus
) -> None:
    repo.add(_note("0001"))  # historique ignoré sans Last-Event-ID
    bus.prime(_note("0002"))
    out = list(stream.events(StreamNotificationsCommand(user_id="u")))
    assert [n.id for n in out if n is not None] == ["0002"]
    assert out[-1] is None  # keep-alive final


def test_replays_missed_then_live(
    stream: NotificationStream, repo: InMemoryNotificationRepository, bus: InMemoryNotificationBus
) -> None:
    for i in (1, 2, 3):
        repo.add(_note(f"000{i}"))
    bus.prime(_note("0004"))
    out = [
        n.id
        for n in stream.events(StreamNotificationsCommand(user_id="u", last_event_id="0001"))
        if n is not None
    ]
    assert out == ["0002", "0003", "0004"]  # 0001 exclu (strictement supérieur), ordre chrono


def test_dedups_backlog_and_live(
    stream: NotificationStream, repo: InMemoryNotificationRepository, bus: InMemoryNotificationBus
) -> None:
    repo.add(_note("0002"))
    bus.prime(_note("0002"))  # même notif rejouée en live
    bus.prime(_note("0003"))
    out = [
        n.id
        for n in stream.events(StreamNotificationsCommand(user_id="u", last_event_id="0001"))
        if n is not None
    ]
    assert out == ["0002", "0003"]  # pas de doublon


def test_other_users_notifications_excluded(
    stream: NotificationStream, repo: InMemoryNotificationRepository, bus: InMemoryNotificationBus
) -> None:
    repo.add(_note("0002", user="someone-else"))
    out = list(stream.events(StreamNotificationsCommand(user_id="u", last_event_id="0001")))
    assert [n for n in out if n is not None] == []
