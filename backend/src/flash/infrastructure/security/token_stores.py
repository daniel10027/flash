"""Implémentations Redis des ports d'authentification (``application.auth.stores``)."""

from __future__ import annotations

from datetime import UTC, datetime

from redis import Redis

from flash.application.auth.stores import DeviceRecord


class RedisRefreshTokenStore:
    def __init__(self, redis: Redis[bytes]) -> None:
        self._redis = redis

    @staticmethod
    def _key(user_id: str, device_id: str) -> str:
        return f"refresh:{user_id}:{device_id}"

    @staticmethod
    def _meta_key(user_id: str, device_id: str) -> str:
        return f"refreshmeta:{user_id}:{device_id}"

    def remember(
        self,
        *,
        user_id: str,
        device_id: str,
        jti: str,
        ttl_seconds: int,
        now: str | None = None,
    ) -> None:
        stamp = now or datetime.now(UTC).isoformat()
        pipe = self._redis.pipeline()
        pipe.set(self._key(user_id, device_id), jti, ex=ttl_seconds)
        meta = self._meta_key(user_id, device_id)
        pipe.hset(meta, "last_seen", stamp)
        pipe.hsetnx(meta, "first_seen", stamp)
        pipe.expire(meta, ttl_seconds)
        pipe.execute()

    def is_current(self, *, user_id: str, device_id: str, jti: str) -> bool:
        stored = self._redis.get(self._key(user_id, device_id))
        return stored is not None and stored.decode() == jti

    def forget(self, *, user_id: str, device_id: str) -> None:
        self._redis.delete(
            self._key(user_id, device_id), self._meta_key(user_id, device_id)
        )

    def forget_all(self, *, user_id: str) -> None:
        keys = list(self._redis.scan_iter(match=f"refresh:{user_id}:*")) + list(
            self._redis.scan_iter(match=f"refreshmeta:{user_id}:*")
        )
        if keys:
            self._redis.delete(*keys)

    def list_devices(self, *, user_id: str) -> list[DeviceRecord]:
        prefix = f"refresh:{user_id}:"
        records: list[DeviceRecord] = []
        for raw in self._redis.scan_iter(match=f"{prefix}*"):
            device_id = raw.decode().removeprefix(prefix)
            meta = self._redis.hgetall(self._meta_key(user_id, device_id))
            records.append(
                DeviceRecord(
                    device_id=device_id,
                    first_seen=meta.get(b"first_seen", b"").decode() or None,
                    last_seen=meta.get(b"last_seen", b"").decode() or None,
                )
            )
        records.sort(key=lambda r: r.last_seen or "", reverse=True)
        return records


class RedisAccessRevocationStore:
    def __init__(self, redis: Redis[bytes]) -> None:
        self._redis = redis

    def revoke(self, jti: str, *, ttl_seconds: int) -> None:
        self._redis.set(f"revoked:{jti}", "1", ex=max(ttl_seconds, 1))

    def is_revoked(self, jti: str) -> bool:
        return self._redis.exists(f"revoked:{jti}") == 1


class RedisRateLimiter:
    def __init__(self, redis: Redis[bytes]) -> None:
        self._redis = redis

    def hit(self, key: str, *, limit: int, per_seconds: int) -> bool:
        window = f"rl:{key}:{per_seconds}"
        pipe = self._redis.pipeline()
        pipe.incr(window)
        pipe.expire(window, per_seconds, nx=True)
        count, _ = pipe.execute()
        return int(count) <= limit


__all__ = ["RedisAccessRevocationStore", "RedisRateLimiter", "RedisRefreshTokenStore"]
