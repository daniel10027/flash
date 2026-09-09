"""Construction d'un ``Deps`` de test entièrement en mémoire."""

from __future__ import annotations

from datetime import timedelta

from flash.application.notifications.dispatcher import NotificationDispatcher
from flash.application.services import AppServices
from flash.domain.limits.limits import KycPolicy, LimitPolicy
from flash.domain.pricing.pricing import PricingService
from flash.infrastructure.card_issuer import SandboxCardIssuer
from flash.infrastructure.codes import PepperedWithdrawalCodes
from flash.infrastructure.documents import InMemoryDocumentStore
from flash.infrastructure.events import NotifyingEventPublisher
from flash.infrastructure.limits import NullLimitCounter, build_limit_repository
from flash.infrastructure.notifications import BusChannel, FanOutNotifier, InAppChannel
from flash.infrastructure.pricing import build_pricing_repository
from flash.infrastructure.reference import MutableReferenceDirectory
from flash.interface.container import Deps
from flash.interface.security.wiring import SecurityBundle
from tests.support.audit import InMemoryAuditLog
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
    card_webhook_secret: str = "test-card-webhook-secret",
    compliance_api_key: str = "test-compliance-key",
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
    reference = MutableReferenceDirectory()
    admin_roles: dict[str, str] = {}
    if admin_api_key.strip():
        admin_roles[admin_api_key.strip()] = "admin"
    if compliance_api_key.strip():
        admin_roles[compliance_api_key.strip()] = "compliance"
    return Deps(
        services=services,
        countries=reference,
        reference=reference,
        reference_editor=reference,
        audit=InMemoryAuditLog(),
        admin_roles=admin_roles,
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
        card_issuer=SandboxCardIssuer(pepper="test-card-pepper-0123456789"),
        card_webhook_secret=card_webhook_secret,
        card_daily_limit_minor=500_000,
        card_monthly_limit_minor=5_000_000,
    )


__all__ = ["build_test_deps"]
