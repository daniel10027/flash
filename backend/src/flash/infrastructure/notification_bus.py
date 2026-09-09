"""Bus temps réel des notifications sur Redis pub/sub.

Un worker publie sur ``flash:notif:<user_id>`` ; un flux SSE tenu par n'importe quel
worker s'y abonne. ``subscribe`` émet ``None`` à chaque expiration du délai d'attente
(occasion d'envoyer un keep-alive SSE et de détecter une déconnexion client).
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import datetime

from redis import Redis

from flash.application.notifications.model import Notification, NotificationKind

_PREFIX = "flash:notif:"
_POLL_TIMEOUT_SECONDS = 15.0


def _channel(user_id: str) -> str:
    return f"{_PREFIX}{user_id}"


def _encode(notification: Notification) -> str:
    payload = notification.to_dict()
    payload["user_id"] = notification.user_id
    payload["kind"] = notification.kind.value
    return json.dumps(payload)


def _decode(raw: bytes | str) -> Notification:
    data = json.loads(raw)
    return Notification(
        id=data["id"],
        user_id=data["user_id"],
        kind=NotificationKind(data["kind"]),
        title=data["title"],
        body=data["body"],
        created_at=datetime.fromisoformat(data["created_at"]),
        data=dict(data.get("data") or {}),
        read_at=datetime.fromisoformat(data["read_at"]) if data.get("read_at") else None,
    )


class RedisNotificationBus:
    def __init__(self, redis: Redis[bytes], *, poll_timeout: float = _POLL_TIMEOUT_SECONDS) -> None:
        self._redis = redis
        self._poll_timeout = poll_timeout

    def publish(self, notification: Notification) -> None:
        self._redis.publish(_channel(notification.user_id), _encode(notification))

    def subscribe(self, user_id: str) -> Iterator[Notification | None]:
        pubsub = self._redis.pubsub(ignore_subscribe_messages=True)
        pubsub.subscribe(_channel(user_id))
        try:
            while True:
                message = pubsub.get_message(timeout=self._poll_timeout)
                if message is None:
                    yield None  # keep-alive
                    continue
                yield _decode(message["data"])
        finally:
            pubsub.close()


__all__ = ["RedisNotificationBus"]
