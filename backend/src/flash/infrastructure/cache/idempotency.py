"""``RedisIdempotencyStore`` — adapter du port ``IdempotencyStore`` sur Redis.

Deux clés par opération :
- ``<key>``         : marqueur "vue" (SET NX EX) pour ``remember`` ;
- ``<key>:result``  : payload JSON du résultat une fois l'opération terminée.
"""

from __future__ import annotations

import json
from typing import Any

from redis import Redis


class RedisIdempotencyStore:
    def __init__(self, redis: Redis[bytes]) -> None:
        self._redis = redis

    def remember(self, key: str, *, ttl_seconds: int) -> bool:
        return bool(self._redis.set(key, "1", nx=True, ex=ttl_seconds))

    def get_result(self, key: str) -> dict[str, Any] | None:
        raw = self._redis.get(f"{key}:result")
        if raw is None:
            return None
        decoded: dict[str, Any] = json.loads(raw)
        return decoded

    def save_result(self, key: str, result: dict[str, Any], *, ttl_seconds: int) -> None:
        self._redis.set(f"{key}:result", json.dumps(result, separators=(",", ":")), ex=ttl_seconds)


__all__ = ["RedisIdempotencyStore"]
