"""Client Redis partagé."""

from __future__ import annotations

from functools import lru_cache

from redis import Redis

from flash.infrastructure.config import get_settings


@lru_cache
def get_redis() -> Redis[bytes]:
    return Redis.from_url(get_settings().redis_url)


__all__ = ["get_redis"]
