"""Composition root : construit les dépendances concrètes et les expose aux blueprints.

C'est le **seul** endroit où l'on choisit les adapters. Les cas d'usage et le domaine
n'en savent rien. En test, on passe un ``Deps`` déjà assemblé avec des fakes.
"""

from __future__ import annotations

from dataclasses import dataclass

from flask import Flask, current_app

from flash.application.ports import OtpService
from flash.application.services import AppServices
from flash.domain.country.directory import CountryDirectory, StaticCountryDirectory
from flash.domain.identity.pin import PinHasher
from flash.infrastructure.cache.idempotency import RedisIdempotencyStore
from flash.infrastructure.cache.redis import get_redis
from flash.infrastructure.clock import SystemClock
from flash.infrastructure.config import Settings
from flash.infrastructure.db.engine import get_session_factory
from flash.infrastructure.db.uow import SqlAlchemyUnitOfWork
from flash.infrastructure.events import LoggingEventPublisher
from flash.infrastructure.ids import Uuid7Generator
from flash.infrastructure.otp import ConsoleOtpChannel, RedisOtpService
from flash.infrastructure.security.pin_hasher import Argon2PinHasher

_EXT_KEY = "flash_deps"


@dataclass(frozen=True, slots=True)
class Deps:
    services: AppServices
    countries: CountryDirectory
    pins: PinHasher
    otp: OtpService


def build_deps(settings: Settings) -> Deps:
    clock = SystemClock()
    session_factory = get_session_factory()
    redis = get_redis()

    services = AppServices(
        uow=lambda: SqlAlchemyUnitOfWork(session_factory, clock),
        clock=clock,
        ids=Uuid7Generator(),
        events=LoggingEventPublisher(),
        idempotency=RedisIdempotencyStore(redis),
    )
    otp = RedisOtpService(
        redis,
        ConsoleOtpChannel(),
        pepper=settings.secret_key,
        ttl_seconds=settings.otp_ttl_seconds,
        max_attempts=settings.otp_max_attempts,
    )
    return Deps(
        services=services,
        countries=StaticCountryDirectory(),
        pins=Argon2PinHasher(),
        otp=otp,
    )


def register_deps(app: Flask, deps: Deps) -> None:
    app.extensions[_EXT_KEY] = deps


def deps() -> Deps:
    bundle = current_app.extensions.get(_EXT_KEY)
    if not isinstance(bundle, Deps):  # pragma: no cover - erreur de câblage
        raise RuntimeError("Dépendances non initialisées : register_deps manquant.")
    return bundle


__all__ = ["Deps", "build_deps", "deps", "register_deps"]
