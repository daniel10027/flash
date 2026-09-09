"""Agrégat ``MerchantWebhookDelivery`` — une notification sortante vers le back-end d'un
marchand (BE-071).

Créée ``PENDING`` quand un événement marchand se produit (paiement encaissé, remboursé).
Le job de livraison la POST sur l'endpoint du marchand, signée HMAC-SHA256. En cas
d'échec, elle est re-tentée jusqu'à ``_MAX_ATTEMPTS`` avec un backoff exponentiel, puis
passe ``FAILED``.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from enum import StrEnum
from typing import Any

from flash.domain.merchants.events import (
    MerchantWebhookDelivered,
    MerchantWebhookExhausted,
)
from flash.domain.shared.errors import InvalidAccountState
from flash.domain.shared.events import EventRecorder
from flash.domain.shared.identifiers import EntityId

_MAX_ATTEMPTS = 6
_BASE_BACKOFF = timedelta(minutes=1)


class MerchantWebhookStatus(StrEnum):
    PENDING = "PENDING"
    DELIVERED = "DELIVERED"
    FAILED = "FAILED"


class MerchantWebhookDelivery(EventRecorder):
    def __init__(
        self,
        *,
        id: EntityId,
        merchant_id: EntityId,
        source_id: EntityId,
        event_type: str,
        payload: dict[str, Any],
        status: MerchantWebhookStatus,
        attempts: int,
        created_at: datetime,
        next_attempt_at: datetime,
        delivered_at: datetime | None = None,
        last_error: str | None = None,
    ) -> None:
        super().__init__()
        self.id = id
        self.merchant_id = merchant_id
        self.source_id = source_id
        self.event_type = event_type
        self.payload = payload
        self.status = status
        self.attempts = attempts
        self.created_at = created_at
        self.next_attempt_at = next_attempt_at
        self.delivered_at = delivered_at
        self.last_error = last_error

    @classmethod
    def enqueue(
        cls,
        *,
        delivery_id: EntityId,
        merchant_id: EntityId,
        source_id: EntityId,
        event_type: str,
        payload: dict[str, Any],
        now: datetime,
    ) -> MerchantWebhookDelivery:
        return cls(
            id=delivery_id,
            merchant_id=merchant_id,
            source_id=source_id,
            event_type=event_type,
            payload=payload,
            status=MerchantWebhookStatus.PENDING,
            attempts=0,
            created_at=now,
            next_attempt_at=now,
        )

    @property
    def is_pending(self) -> bool:
        return self.status is MerchantWebhookStatus.PENDING

    def due(self, now: datetime) -> bool:
        return self.is_pending and now >= self.next_attempt_at

    def _ensure_pending(self) -> None:
        if not self.is_pending:
            raise InvalidAccountState(
                "Cette livraison de webhook est déjà résolue.", status=self.status.value
            )

    def record_success(self, now: datetime) -> None:
        self._ensure_pending()
        self.attempts += 1
        self.status = MerchantWebhookStatus.DELIVERED
        self.delivered_at = now
        self.last_error = None
        self.record_event(
            MerchantWebhookDelivered(
                occurred_at=now,
                aggregate_id=str(self.id),
                merchant_id=str(self.merchant_id),
                event_type=self.event_type,
                attempts=self.attempts,
            )
        )

    def record_failure(self, *, error: str, now: datetime) -> None:
        self._ensure_pending()
        self.attempts += 1
        self.last_error = error[:200]
        if self.attempts >= _MAX_ATTEMPTS:
            self.status = MerchantWebhookStatus.FAILED
            self.record_event(
                MerchantWebhookExhausted(
                    occurred_at=now,
                    aggregate_id=str(self.id),
                    merchant_id=str(self.merchant_id),
                    event_type=self.event_type,
                    attempts=self.attempts,
                    last_error=self.last_error,
                )
            )
        else:
            self.next_attempt_at = now + _BASE_BACKOFF * (2 ** (self.attempts - 1))

    def __repr__(self) -> str:
        return (
            f"MerchantWebhookDelivery(type={self.event_type!r}, "
            f"status={self.status.value}, attempts={self.attempts})"
        )


__all__ = ["MerchantWebhookDelivery", "MerchantWebhookStatus"]
