"""Implémentations Redis des ports d'authentification (``application.auth.stores``)."""

from __future__ import annotations

from redis import Redis


class RedisRefreshTokenStore:
    def __init__(self, redis: Redis[bytes]) -> None:
        self._redis = redis

    @staticmethod
    def _key(user_id: str, device_id: str) -> str:
        return f"refresh:{user_id}:{device_id}"

    def remember(self, *, user_id: str, device_id: str, jti: str, ttl_seconds: int) -> None:
        self._redis.set(self._key(user_id, device_id), jti, ex=ttl_seconds)

    def is_current(self, *, user_id: str, device_id: str, jti: str) -> bool:
        stored = self._redis.get(self._key(user_id, device_id))
        return stored is not None and stored.decode() == jti

    def forget(self, *, user_id: str, device_id: str) -> None:
        self._redis.delete(self._key(user_id, device_id))


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
