"""Composition root : construit les dépendances concrètes et les expose aux blueprints.

C'est le **seul** endroit où l'on choisit les adapters. Les cas d'usage et le domaine
n'en savent rien. En test, on passe un ``Deps`` déjà assemblé avec des fakes.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from flask import Flask, current_app

from flash.application.auth.tokens import TokenService
from flash.application.cash.ports import WithdrawalCodes
from flash.application.identity.documents import DocumentStore
from flash.application.notifications.dispatcher import NotificationDispatcher
from flash.application.notifications.ports import NotificationBus, NotificationRepository
from flash.application.ports import OtpService
from flash.application.services import AppServices
from flash.domain.country.directory import CountryDirectory, StaticCountryDirectory
from flash.domain.identity.pin import PinHasher
from flash.domain.limits.limits import KycPolicy, LimitPolicy
from flash.domain.pricing.pricing import PricingService
from flash.infrastructure.cache.idempotency import RedisIdempotencyStore
from flash.infrastructure.cache.redis import get_redis
from flash.infrastructure.clock import SystemClock
from flash.infrastructure.codes import PepperedWithdrawalCodes
from flash.infrastructure.config import Settings
from flash.infrastructure.db.engine import get_session_factory
from flash.infrastructure.db.notification_repository import SqlAlchemyNotificationRepository
from flash.infrastructure.db.uow import SqlAlchemyUnitOfWork
from flash.infrastructure.documents import LocalFilesystemDocumentStore
from flash.infrastructure.events import LoggingEventPublisher, NotifyingEventPublisher
from flash.infrastructure.ids import Uuid7Generator
from flash.infrastructure.limits import NullLimitCounter, build_limit_repository
from flash.infrastructure.notification_bus import RedisNotificationBus
from flash.infrastructure.notifications import (
    BusChannel,
    FanOutNotifier,
    FcmPushChannel,
    InAppChannel,
    LoggingNotificationChannel,
    SmtpEmailChannel,
)
from flash.infrastructure.otp import ConsoleOtpChannel, RedisOtpService
from flash.infrastructure.pricing import build_pricing_repository
from flash.infrastructure.security.pin_hasher import Argon2PinHasher

_EXT_KEY = "flash_deps"


@dataclass(frozen=True, slots=True)
class Deps:
    services: AppServices
    countries: CountryDirectory
    pins: PinHasher
    otp: OtpService
    tokens: TokenService
    pricing: PricingService
    limits: LimitPolicy
    kyc: KycPolicy
    codes: WithdrawalCodes
    documents: DocumentStore
    admin_api_key: str
    reversal_window: timedelta
    notifications: NotificationRepository
    notification_bus: NotificationBus


def build_app_services(settings: Settings) -> AppServices:
    clock = SystemClock()
    ids = Uuid7Generator()
    session_factory = get_session_factory()

    notifier = FanOutNotifier(
        [
            InAppChannel(SqlAlchemyNotificationRepository(session_factory)),
            BusChannel(RedisNotificationBus(get_redis())),
            SmtpEmailChannel(
                host=settings.smtp_host, port=settings.smtp_port, sender=settings.smtp_from
            ),
            FcmPushChannel(credentials_json=settings.fcm_credentials_json),
            LoggingNotificationChannel(),
        ]
    )
    dispatcher = NotificationDispatcher(notifier=notifier, clock=clock, ids=ids)

    return AppServices(
        uow=lambda: SqlAlchemyUnitOfWork(session_factory, clock),
        clock=clock,
        ids=ids,
        events=NotifyingEventPublisher(LoggingEventPublisher(), dispatcher),
        idempotency=RedisIdempotencyStore(get_redis()),
    )


def build_deps(settings: Settings, *, tokens: TokenService) -> Deps:
    redis = get_redis()
    services = build_app_services(settings)
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
        tokens=tokens,
        pricing=PricingService(build_pricing_repository()),
        limits=LimitPolicy(build_limit_repository(), NullLimitCounter()),
        kyc=KycPolicy(),
        codes=PepperedWithdrawalCodes(settings.secret_key),
        documents=LocalFilesystemDocumentStore(settings.kyc_document_dir),
        admin_api_key=settings.admin_api_key,
        reversal_window=timedelta(seconds=settings.reversal_window_seconds),
        notifications=SqlAlchemyNotificationRepository(get_session_factory()),
        notification_bus=RedisNotificationBus(get_redis()),
    )


def register_deps(app: Flask, deps: Deps) -> None:
    app.extensions[_EXT_KEY] = deps


def deps() -> Deps:
    bundle = current_app.extensions.get(_EXT_KEY)
    if not isinstance(bundle, Deps):  # pragma: no cover - erreur de câblage
        raise RuntimeError("Dépendances non initialisées : register_deps manquant.")
    return bundle


__all__ = ["Deps", "build_app_services", "build_deps", "deps", "register_deps"]
