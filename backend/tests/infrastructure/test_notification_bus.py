"""Tests de RedisNotificationBus : encodage et boucle subscribe (BE-042)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from flash.application.notifications.model import Notification, NotificationKind
from flash.infrastructure.notification_bus import RedisNotificationBus, _decode, _encode

T0 = datetime(2026, 1, 1, 12, 30, tzinfo=UTC)


def _note() -> Notification:
    return Notification(
        id="01a00000-0000-7000-8000-000000000001",
        user_id="u-1",
        kind=NotificationKind.MONEY_IN,
        title="Argent reçu",
        body="Vous avez reçu 10 000 XOF.",
        created_at=T0,
        data={"reference": "TRX-1"},
        read_at=None,
    )


def test_encode_decode_roundtrip() -> None:
    original = _note()
    restored = _decode(_encode(original))
    assert restored == original


class _FakePubSub:
    def __init__(self, script: list[dict[str, Any] | None]) -> None:
        self._script = list(script)
        self.subscribed: list[str] = []
        self.closed = False

    def subscribe(self, channel: str) -> None:
        self.subscribed.append(channel)

    def get_message(self, *, timeout: float) -> dict[str, Any] | None:
        return self._script.pop(0) if self._script else None  # None = expiration (réel)

    def close(self) -> None:
        self.closed = True


class _FakeRedis:
    def __init__(self, pubsub: _FakePubSub) -> None:
        self._pubsub = pubsub
        self.published: list[tuple[str, str]] = []

    def publish(self, channel: str, message: str) -> None:
        self.published.append((channel, message))

    def pubsub(self, *, ignore_subscribe_messages: bool = False) -> _FakePubSub:
        return self._pubsub


def test_publish_targets_user_channel() -> None:
    fake = _FakeRedis(_FakePubSub([]))
    RedisNotificationBus(fake).publish(_note())  # type: ignore[arg-type]
    assert fake.published[0][0] == "flash:notif:u-1"


def test_subscribe_yields_keepalive_then_notification() -> None:
    encoded = _encode(_note())
    pubsub = _FakePubSub([None, {"data": encoded.encode()}])
    bus = RedisNotificationBus(_FakeRedis(pubsub), poll_timeout=0.01)  # type: ignore[arg-type]

    gen = bus.subscribe("u-1")
    seen = [next(gen), next(gen)]
    gen.close()  # type: ignore[attr-defined]  # c'est un générateur
    assert seen[0] is None
    assert isinstance(seen[1], Notification) and seen[1].id.endswith("0001")
    assert pubsub.subscribed == ["flash:notif:u-1"]
    assert pubsub.closed is True
