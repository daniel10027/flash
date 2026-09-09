"""Webhooks marchand (BE-071) : config, mise en file sur événement, job de livraison."""

from __future__ import annotations

import json
from uuid import UUID

import pytest

from flash.application.merchants.operations import NotAMerchant
from flash.application.merchants.webhooks import (
    ClearMerchantWebhook,
    ClearMerchantWebhookCommand,
    ConfigureMerchantWebhook,
    ConfigureMerchantWebhookCommand,
    DispatchMerchantWebhooks,
    MerchantWebhookEnqueuer,
)
from flash.application.services import AppServices
from flash.domain.merchants.events import (
    MerchantPaymentCompleted,
    MerchantPaymentRefunded,
)
from flash.domain.merchants.merchant import Merchant
from flash.domain.merchants.webhook import MerchantWebhookStatus
from flash.domain.shared.errors import InvalidInput
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import XOF
from tests.support.fakes import (
    FixedClock,
    InMemoryIdempotencyStore,
    RecordingEventPublisher,
    SeqIdGenerator,
)
from tests.support.repositories import InMemoryUnitOfWork
from tests.support.webhooks import RecordingMerchantWebhookSender

MID = EntityId(str(UUID(int=9)))
UID = str(UUID(int=9))
PAYMENT_ID = str(UUID(int=100))
SECRET = "a-sixteen-char-secret!"
URL = "https://shop.example.com/hook"


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def services(uow: InMemoryUnitOfWork, clock: FixedClock) -> AppServices:
    return AppServices(
        uow=lambda: uow,
        clock=clock,
        ids=SeqIdGenerator(),
        events=RecordingEventPublisher(),
        idempotency=InMemoryIdempotencyStore(),
    )


def _merchant(uow: InMemoryUnitOfWork, *, with_webhook: bool = False) -> None:
    merchant = Merchant.enroll(
        merchant_id=MID,
        user_id=EntityId(UID),
        display_name="Chez Awa",
        category="RESTAURANT",
        currency=XOF,
        fee_bps=100,
        now=FixedClock().now(),
    )
    if with_webhook:
        merchant.configure_webhook(url=URL, secret=SECRET, now=FixedClock().now())
    merchant.pull_events()
    uow.merchants.add(merchant)


def _completed_event() -> MerchantPaymentCompleted:
    return MerchantPaymentCompleted(
        occurred_at=FixedClock().now(),
        aggregate_id=PAYMENT_ID,
        payer_id=str(UUID(int=1)),
        merchant_id=str(MID),
        amount_minor=25_000,
        fee_minor=250,
        currency="XOF",
        reference="Cmd 1",
    )


class TestConfigure:
    def test_configure_then_clear(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _merchant(uow)
        view = ConfigureMerchantWebhook(services=services).execute(
            ConfigureMerchantWebhookCommand(merchant_user_id=UID, url=URL, secret=SECRET)
        )
        assert view.configured is True and view.endpoint == URL
        assert view.to_dict() == {"endpoint": URL, "configured": True}
        merchant = uow.merchants.get(MID)
        assert merchant is not None and merchant.has_webhook

        cleared = ClearMerchantWebhook(services=services).execute(
            ClearMerchantWebhookCommand(merchant_user_id=UID)
        )
        assert cleared.configured is False
        assert uow.merchants.get(MID).has_webhook is False  # type: ignore[union-attr]

    def test_configure_rejects_bad_url(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _merchant(uow)
        with pytest.raises(InvalidInput):
            ConfigureMerchantWebhook(services=services).execute(
                ConfigureMerchantWebhookCommand(
                    merchant_user_id=UID, url="ftp://x", secret=SECRET
                )
            )

    def test_non_merchant_rejected(self, services: AppServices) -> None:
        with pytest.raises(NotAMerchant):
            ConfigureMerchantWebhook(services=services).execute(
                ConfigureMerchantWebhookCommand(merchant_user_id=UID, url=URL, secret=SECRET)
            )
        with pytest.raises(NotAMerchant):
            ClearMerchantWebhook(services=services).execute(
                ClearMerchantWebhookCommand(merchant_user_id=UID)
            )


class TestEnqueuer:
    def _enqueuer(self, uow: InMemoryUnitOfWork, clock: FixedClock) -> MerchantWebhookEnqueuer:
        return MerchantWebhookEnqueuer(
            uow_factory=lambda: uow, ids=SeqIdGenerator(), clock=clock
        )

    def test_enqueues_on_payment_completed(
        self, uow: InMemoryUnitOfWork, clock: FixedClock
    ) -> None:
        _merchant(uow, with_webhook=True)
        self._enqueuer(uow, clock).handle([_completed_event()])
        due = uow.merchant_webhooks.list_due(clock.now())
        assert len(due) == 1
        assert due[0].event_type == "payment.completed"
        assert due[0].payload["type"] == "payment.completed"

    def test_enqueues_on_payment_refunded(
        self, uow: InMemoryUnitOfWork, clock: FixedClock
    ) -> None:
        _merchant(uow, with_webhook=True)
        event = MerchantPaymentRefunded(
            occurred_at=clock.now(),
            aggregate_id=PAYMENT_ID,
            payer_id=str(UUID(int=1)),
            merchant_id=str(MID),
            amount_minor=25_000,
            fee_minor=250,
            currency="XOF",
            reference="Cmd 1",
            reversal_transaction_id=str(UUID(int=2)),
        )
        self._enqueuer(uow, clock).handle([event])
        assert uow.merchant_webhooks.list_due(clock.now())[0].event_type == "payment.refunded"

    def test_skips_when_no_webhook_configured(
        self, uow: InMemoryUnitOfWork, clock: FixedClock
    ) -> None:
        _merchant(uow, with_webhook=False)
        self._enqueuer(uow, clock).handle([_completed_event()])
        assert uow.merchant_webhooks.list_due(clock.now()) == []

    def test_ignores_unrelated_events(
        self, uow: InMemoryUnitOfWork, clock: FixedClock
    ) -> None:
        _merchant(uow, with_webhook=True)
        self._enqueuer(uow, clock).handle([])
        assert uow.merchant_webhooks.list_due(clock.now()) == []

    def test_is_idempotent_per_source(
        self, uow: InMemoryUnitOfWork, clock: FixedClock
    ) -> None:
        _merchant(uow, with_webhook=True)
        enqueuer = self._enqueuer(uow, clock)
        enqueuer.handle([_completed_event()])
        enqueuer.handle([_completed_event()])
        assert len(uow.merchant_webhooks.list_due(clock.now())) == 1


class TestDispatchJob:
    def _enqueue(self, uow: InMemoryUnitOfWork, clock: FixedClock) -> None:
        MerchantWebhookEnqueuer(
            uow_factory=lambda: uow, ids=SeqIdGenerator(), clock=clock
        ).handle([_completed_event()])

    def test_delivers_and_signs(
        self, services: AppServices, uow: InMemoryUnitOfWork, clock: FixedClock
    ) -> None:
        _merchant(uow, with_webhook=True)
        self._enqueue(uow, clock)
        sender = RecordingMerchantWebhookSender()
        report = DispatchMerchantWebhooks(services=services, sender=sender).execute()
        assert report.due == 1 and report.delivered == 1
        assert sender.calls[0]["url"] == URL
        assert sender.calls[0]["secret"] == SECRET
        assert json.loads(sender.calls[0]["body"])["type"] == "payment.completed"  # type: ignore[arg-type]
        delivery = uow.merchant_webhooks.get(EntityId(str(UUID(int=1))))
        assert delivery is not None and delivery.status is MerchantWebhookStatus.DELIVERED

    def test_retries_then_succeeds(
        self, services: AppServices, uow: InMemoryUnitOfWork, clock: FixedClock
    ) -> None:
        _merchant(uow, with_webhook=True)
        self._enqueue(uow, clock)
        sender = RecordingMerchantWebhookSender(fail_until=1)
        first = DispatchMerchantWebhooks(services=services, sender=sender).execute()
        assert first.retried == 1 and first.delivered == 0

        clock.advance(minutes=5)
        second = DispatchMerchantWebhooks(services=services, sender=sender).execute()
        assert second.delivered == 1

    def test_exhausts_after_max_attempts(
        self, services: AppServices, uow: InMemoryUnitOfWork, clock: FixedClock
    ) -> None:
        _merchant(uow, with_webhook=True)
        self._enqueue(uow, clock)
        sender = RecordingMerchantWebhookSender(fail_until=99)
        for _ in range(6):
            DispatchMerchantWebhooks(services=services, sender=sender).execute()
            clock.advance(hours=2)
        report = DispatchMerchantWebhooks(services=services, sender=sender).execute()
        assert report.due == 0  # plus rien en attente
        delivery = uow.merchant_webhooks.get(EntityId(str(UUID(int=1))))
        assert delivery is not None and delivery.status is MerchantWebhookStatus.FAILED

    def test_marks_failed_when_webhook_removed_mid_flight(
        self, services: AppServices, uow: InMemoryUnitOfWork, clock: FixedClock
    ) -> None:
        _merchant(uow, with_webhook=True)
        self._enqueue(uow, clock)
        merchant = uow.merchants.get(MID)
        assert merchant is not None
        merchant.clear_webhook(clock.now())
        uow.merchants.save(merchant)
        report = DispatchMerchantWebhooks(
            services=services, sender=RecordingMerchantWebhookSender()
        ).execute()
        assert report.retried == 1

    def test_nothing_due_is_noop(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        _merchant(uow, with_webhook=True)
        report = DispatchMerchantWebhooks(
            services=services, sender=RecordingMerchantWebhookSender()
        ).execute()
        assert report.to_dict() == {"due": 0, "delivered": 0, "retried": 0, "exhausted": 0}
