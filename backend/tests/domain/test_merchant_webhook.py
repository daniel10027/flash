"""Tests de ``MerchantWebhookDelivery`` et de la config webhook de ``Merchant`` (BE-071)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from flash.domain.merchants.merchant import Merchant, MerchantStatus
from flash.domain.merchants.webhook import (
    MerchantWebhookDelivery,
    MerchantWebhookStatus,
)
from flash.domain.shared.errors import InvalidAccountState, InvalidInput
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import XOF

T0 = datetime(2026, 1, 1, tzinfo=UTC)
DID = EntityId(str(UUID(int=1)))
MID = EntityId(str(UUID(int=2)))
SRC = EntityId(str(UUID(int=3)))
SECRET = "a-sixteen-char-secret!"


def _merchant() -> Merchant:
    return Merchant(
        id=MID,
        user_id=EntityId(str(UUID(int=9))),
        display_name="Chez Awa",
        category="RESTAURANT",
        currency=XOF,
        fee_bps=100,
        created_at=T0,
        status=MerchantStatus.ACTIVE,
    )


class TestMerchantWebhookConfig:
    def test_configure_sets_url_and_secret(self) -> None:
        merchant = _merchant()
        merchant.configure_webhook(
            url="https://shop.example.com/hook", secret=SECRET, now=T0
        )
        assert merchant.has_webhook is True
        assert merchant.webhook_url == "https://shop.example.com/hook"
        assert [e.name for e in merchant.pull_events()] == ["MerchantWebhookConfigured"]

    def test_configure_rejects_non_http_url(self) -> None:
        with pytest.raises(InvalidInput, match="http"):
            _merchant().configure_webhook(url="ftp://x", secret=SECRET, now=T0)

    def test_configure_rejects_short_secret(self) -> None:
        with pytest.raises(InvalidInput, match="16"):
            _merchant().configure_webhook(
                url="https://x.example.com", secret="short", now=T0
            )

    def test_clear_removes_config(self) -> None:
        merchant = _merchant()
        merchant.configure_webhook(url="https://x.example.com", secret=SECRET, now=T0)
        merchant.pull_events()
        merchant.clear_webhook(T0)
        assert merchant.has_webhook is False
        assert merchant.webhook_url is None
        assert [e.name for e in merchant.pull_events()] == ["MerchantWebhookConfigured"]


class TestMerchantWebhookDelivery:
    def _delivery(self) -> MerchantWebhookDelivery:
        return MerchantWebhookDelivery.enqueue(
            delivery_id=DID,
            merchant_id=MID,
            source_id=SRC,
            event_type="payment.completed",
            payload={"type": "payment.completed"},
            now=T0,
        )

    def test_enqueue_is_pending_and_due_now(self) -> None:
        delivery = self._delivery()
        assert delivery.is_pending
        assert delivery.due(T0) is True
        assert delivery.attempts == 0

    def test_record_success(self) -> None:
        delivery = self._delivery()
        delivery.record_success(T0)
        assert delivery.status is MerchantWebhookStatus.DELIVERED
        assert delivery.attempts == 1
        assert delivery.delivered_at == T0
        assert [e.name for e in delivery.pull_events()] == ["MerchantWebhookDelivered"]

    def test_failure_schedules_backoff_then_exhausts(self) -> None:
        delivery = self._delivery()
        delivery.record_failure(error="HTTP 503", now=T0)
        assert delivery.status is MerchantWebhookStatus.PENDING
        assert delivery.next_attempt_at == T0 + timedelta(minutes=1)
        assert delivery.due(T0) is False
        assert delivery.due(T0 + timedelta(minutes=1)) is True

        for i in range(2, 7):
            delivery.record_failure(error="HTTP 503", now=T0)
            if i < 6:
                assert delivery.status is MerchantWebhookStatus.PENDING
        assert delivery.status is MerchantWebhookStatus.FAILED
        assert delivery.attempts == 6
        assert [e.name for e in delivery.pull_events()] == ["MerchantWebhookExhausted"]

    def test_backoff_is_exponential(self) -> None:
        delivery = self._delivery()
        delivery.record_failure(error="e", now=T0)
        delivery.record_failure(error="e", now=T0)
        assert delivery.next_attempt_at == T0 + timedelta(minutes=2)

    def test_cannot_resolve_twice(self) -> None:
        delivery = self._delivery()
        delivery.record_success(T0)
        with pytest.raises(InvalidAccountState, match="déjà résolue"):
            delivery.record_failure(error="late", now=T0)

    def test_long_error_is_truncated(self) -> None:
        delivery = self._delivery()
        delivery.record_failure(error="x" * 500, now=T0)
        assert delivery.last_error is not None and len(delivery.last_error) == 200

    def test_repr(self) -> None:
        assert "payment.completed" in repr(self._delivery())
