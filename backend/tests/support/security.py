"""Implémentations en mémoire des ports de sécurité, pour les tests."""

from __future__ import annotations

import time

from flash.application.auth.stores import (
    AccessRevocationStore,
    DeviceRecord,
    RateLimiter,
    RefreshTokenStore,
)
from flash.application.auth.tokens import TokenService
from flash.domain.shared.ports import Clock
from flash.infrastructure.security.jwt_codec import JwtTokenCodec
from flash.interface.security.wiring import SecurityBundle


class InMemoryRefreshTokenStore:
    def __init__(self) -> None:
        self._current: dict[tuple[str, str], str] = {}
        self._meta: dict[tuple[str, str], tuple[str, str]] = {}

    def remember(
        self,
        *,
        user_id: str,
        device_id: str,
        jti: str,
        ttl_seconds: int,
        now: str | None = None,
    ) -> None:
        self._current[(user_id, device_id)] = jti
        stamp = now or f"seen-{len(self._meta)}"
        first = self._meta.get((user_id, device_id), (stamp, stamp))[0]
        self._meta[(user_id, device_id)] = (first, stamp)

    def is_current(self, *, user_id: str, device_id: str, jti: str) -> bool:
        return self._current.get((user_id, device_id)) == jti

    def forget(self, *, user_id: str, device_id: str) -> None:
        self._current.pop((user_id, device_id), None)
        self._meta.pop((user_id, device_id), None)

    def forget_all(self, *, user_id: str) -> None:
        for key in [k for k in self._current if k[0] == user_id]:
            self._current.pop(key, None)
            self._meta.pop(key, None)

    def list_devices(self, *, user_id: str) -> list[DeviceRecord]:
        rows = [
            DeviceRecord(device_id=d, first_seen=meta[0], last_seen=meta[1])
            for (u, d), meta in self._meta.items()
            if u == user_id
        ]
        rows.sort(key=lambda r: r.last_seen or "", reverse=True)
        return rows


class InMemoryAccessRevocationStore:
    def __init__(self) -> None:
        self._revoked: set[str] = set()

    def revoke(self, jti: str, *, ttl_seconds: int) -> None:
        self._revoked.add(jti)

    def is_revoked(self, jti: str) -> bool:
        return jti in self._revoked


class InMemoryRateLimiter:
    """Fenêtre fixe basée sur l'horloge réelle (les tests utilisent des fenêtres courtes)."""

    def __init__(self) -> None:
        self._counters: dict[tuple[str, int], int] = {}

    def hit(self, key: str, *, limit: int, per_seconds: int) -> bool:
        window = int(time.time()) // per_seconds
        slot = (key, window)
        self._counters[slot] = self._counters.get(slot, 0) + 1
        return self._counters[slot] <= limit


def build_test_security(
    *,
    secret: str = "flash-test-secret-please-ignore-0123456789abcd",
    access_ttl_seconds: int = 900,
    refresh_ttl_seconds: int = 3600,
    clock: Clock | None = None,
    rate_limiter: RateLimiter | None = None,
    refresh_store: RefreshTokenStore | None = None,
    revocation_store: AccessRevocationStore | None = None,
) -> SecurityBundle:
    store = refresh_store or InMemoryRefreshTokenStore()
    tokens = TokenService(
        codec=JwtTokenCodec(secret, clock=clock),
        access_ttl_seconds=access_ttl_seconds,
        refresh_ttl_seconds=refresh_ttl_seconds,
        refresh_store=store,
        revocation_store=revocation_store or InMemoryAccessRevocationStore(),
    )
    return SecurityBundle(
        tokens=tokens,
        rate_limiter=rate_limiter or InMemoryRateLimiter(),
        refresh_store=store,
    )


__all__ = [
    "InMemoryAccessRevocationStore",
    "InMemoryRateLimiter",
    "InMemoryRefreshTokenStore",
    "build_test_security",
]
