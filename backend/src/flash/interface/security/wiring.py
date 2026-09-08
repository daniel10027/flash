"""Assemblage des services de sécurité et accès depuis les requêtes Flask."""

from __future__ import annotations

from dataclasses import dataclass

from flask import current_app

from flash.application.auth.stores import RateLimiter
from flash.application.auth.tokens import TokenService
from flash.infrastructure.cache.redis import get_redis
from flash.infrastructure.clock import SystemClock
from flash.infrastructure.config import Settings
from flash.infrastructure.security.jwt_codec import JwtTokenCodec
from flash.infrastructure.security.token_stores import (
    RedisAccessRevocationStore,
    RedisRateLimiter,
    RedisRefreshTokenStore,
)

_EXT_KEY = "flash_security"


@dataclass(frozen=True, slots=True)
class SecurityBundle:
    tokens: TokenService
    rate_limiter: RateLimiter


def build_security(settings: Settings) -> SecurityBundle:
    redis = get_redis()
    clock = SystemClock()
    tokens = TokenService(
        codec=JwtTokenCodec(settings.secret_key, clock=clock),
        access_ttl_seconds=settings.jwt_access_ttl_seconds,
        refresh_ttl_seconds=settings.jwt_refresh_ttl_seconds,
        refresh_store=RedisRefreshTokenStore(redis),
        revocation_store=RedisAccessRevocationStore(redis),
    )
    return SecurityBundle(tokens=tokens, rate_limiter=RedisRateLimiter(redis))


def register_security(app: object, bundle: SecurityBundle) -> None:
    app.extensions[_EXT_KEY] = bundle  # type: ignore[attr-defined]


def security() -> SecurityBundle:
    bundle = current_app.extensions.get(_EXT_KEY)
    if not isinstance(bundle, SecurityBundle):  # pragma: no cover - erreur de câblage
        raise RuntimeError("Sécurité non initialisée : appeler register_security dans create_app.")
    return bundle


__all__ = ["SecurityBundle", "build_security", "register_security", "security"]
