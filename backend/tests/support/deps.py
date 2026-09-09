"""Construction d'un ``Deps`` de test entièrement en mémoire."""

from __future__ import annotations

from datetime import timedelta

from flash.application.notifications.dispatcher import NotificationDispatcher
from flash.application.services import AppServices
from flash.domain.country.directory import StaticCountryDirectory
from flash.domain.limits.limits import KycPolicy, LimitPolicy
from flash.domain.pricing.pricing import PricingService
from flash.infrastructure.codes import PepperedWithdrawalCodes
from flash.infrastructure.documents import InMemoryDocumentStore
from flash.infrastructure.events import NotifyingEventPublisher
from flash.infrastructure.limits import NullLimitCounter, build_limit_repository
from flash.infrastructure.notifications import BusChannel, FanOutNotifier, InAppChannel
from flash.infrastructure.pricing import build_pricing_repository
from flash.interface.container import Deps
from flash.interface.security.wiring import SecurityBundle
from tests.support.fakes import (
    FakePinHasher,
    FixedClock,
    InMemoryIdempotencyStore,
    RecordingEventPublisher,
    SeqIdGenerator,
)
from tests.support.notifications import (
    InMemoryNotificationBus,
    InMemoryNotificationRepository,
)
from tests.support.otp import RecordingOtpService
from tests.support.repositories import InMemoryUnitOfWork
from tests.support.security import build_test_security


def build_test_deps(
    *,
    uow: InMemoryUnitOfWork,
    otp: RecordingOtpService,
    bundle: SecurityBundle | None = None,
    clock: FixedClock | None = None,
    admin_api_key: str = "test-admin-key",
) -> Deps:
    bundle = bundle or build_test_security()
    the_clock = clock or FixedClock()
    ids = SeqIdGenerator()
    notifications = InMemoryNotificationRepository()
    notification_bus = InMemoryNotificationBus()
    dispatcher = NotificationDispatcher(
        notifier=FanOutNotifier([InAppChannel(notifications), BusChannel(notification_bus)]),
        clock=the_clock,
        ids=ids,
    )
    services = AppServices(
        uow=lambda: uow,
        clock=the_clock,
        ids=ids,
        events=NotifyingEventPublisher(RecordingEventPublisher(), dispatcher),
        idempotency=InMemoryIdempotencyStore(),
    )
    return Deps(
        services=services,
        countries=StaticCountryDirectory(),
        pins=FakePinHasher(),
        otp=otp,
        tokens=bundle.tokens,
        pricing=PricingService(build_pricing_repository()),
        limits=LimitPolicy(build_limit_repository(), NullLimitCounter()),
        kyc=KycPolicy(),
        codes=PepperedWithdrawalCodes("test-pepper-0123456789"),
        documents=InMemoryDocumentStore(),
        admin_api_key=admin_api_key,
        reversal_window=timedelta(hours=1),
        notifications=notifications,
        notification_bus=notification_bus,
    )


__all__ = ["build_test_deps"]
