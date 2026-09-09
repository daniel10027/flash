"""Webhooks marchand signés (BE-071).

- ``ConfigureMerchantWebhook`` / ``ClearMerchantWebhook`` : le marchand déclare l'URL de
  son back-end et un secret partagé.
- ``MerchantWebhookEnqueuer`` : consommateur d'événements (chaîné après le dispatcher de
  notifications) — sur un paiement encaissé / remboursé, il met une livraison en file si
  le marchand a un webhook configuré. Idempotent par ``(event_type, payment_id)``.
- ``DispatchMerchantWebhooks`` : job qui POST les livraisons échues, signées HMAC-SHA256,
  avec re-tentatives à backoff exponentiel (``MerchantWebhookDelivery``).
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from flash.application.merchants.operations import NotAMerchant
from flash.application.services import AppServices, UnitOfWorkFactory
from flash.application.transaction import execute_in_uow
from flash.application.unit_of_work import WorkUnitOfWork
from flash.application.use_case import Command, UseCase
from flash.domain.merchants.events import MerchantPaymentCompleted, MerchantPaymentRefunded
from flash.domain.merchants.webhook import MerchantWebhookDelivery
from flash.domain.shared.events import DomainEvent
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.ports import Clock, IdGenerator

_EVENT_BY_TYPE: dict[type[DomainEvent], str] = {
    MerchantPaymentCompleted: "payment.completed",
    MerchantPaymentRefunded: "payment.refunded",
}


# ============================================================== configuration
@dataclass(frozen=True, slots=True)
class ConfigureMerchantWebhookCommand(Command):
    merchant_user_id: str
    url: str
    secret: str


@dataclass(frozen=True, slots=True)
class MerchantWebhookView:
    endpoint: str | None
    configured: bool

    def to_dict(self) -> dict[str, Any]:
        return {"endpoint": self.endpoint, "configured": self.configured}


class ConfigureMerchantWebhook(
    UseCase[ConfigureMerchantWebhookCommand, MerchantWebhookView]
):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: ConfigureMerchantWebhookCommand) -> MerchantWebhookView:
        now = self._services.clock.now()
        captured: list[MerchantWebhookView] = []

        def work(uow: WorkUnitOfWork) -> None:
            merchant = uow.merchants.get_by_user_id(EntityId(command.merchant_user_id))
            if merchant is None:
                raise NotAMerchant()
            merchant.configure_webhook(url=command.url, secret=command.secret, now=now)
            uow.merchants.save(merchant)
            captured.append(MerchantWebhookView(endpoint=merchant.webhook_url, configured=True))

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


@dataclass(frozen=True, slots=True)
class ClearMerchantWebhookCommand(Command):
    merchant_user_id: str


class ClearMerchantWebhook(UseCase[ClearMerchantWebhookCommand, MerchantWebhookView]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: ClearMerchantWebhookCommand) -> MerchantWebhookView:
        now = self._services.clock.now()

        def work(uow: WorkUnitOfWork) -> None:
            merchant = uow.merchants.get_by_user_id(EntityId(command.merchant_user_id))
            if merchant is None:
                raise NotAMerchant()
            merchant.clear_webhook(now)
            uow.merchants.save(merchant)

        execute_in_uow(self._services.uow, self._services.events, work)
        return MerchantWebhookView(endpoint=None, configured=False)


# ============================================================== mise en file
def _payload_for(event: DomainEvent, event_type: str) -> dict[str, Any]:
    base = event.to_payload()
    return {
        "type": event_type,
        "occurred_at": event.occurred_at.isoformat(),
        "data": base,
    }


class MerchantWebhookEnqueuer:
    """Consommateur d'événements : ``handle`` ouvre sa propre UoW (best-effort)."""

    def __init__(self, *, uow_factory: UnitOfWorkFactory, ids: IdGenerator, clock: Clock) -> None:
        self._uow_factory = uow_factory
        self._ids = ids
        self._clock = clock

    def handle(self, events: Iterable[DomainEvent]) -> None:
        relevant = [(e, _EVENT_BY_TYPE[type(e)]) for e in events if type(e) in _EVENT_BY_TYPE]
        if not relevant:
            return
        now = self._clock.now()
        with self._uow_factory() as uow:
            for event, event_type in relevant:
                merchant_id = getattr(event, "merchant_id", None)
                if merchant_id is None:  # pragma: no cover - garde défensive
                    continue
                merchant = uow.merchants.get(EntityId(str(merchant_id)))
                if merchant is None or not merchant.has_webhook:
                    continue
                source_id = EntityId(str(event.aggregate_id))
                if uow.merchant_webhooks.exists_for_source(event_type, source_id):
                    continue
                uow.merchant_webhooks.add(
                    MerchantWebhookDelivery.enqueue(
                        delivery_id=self._ids.new_id(),
                        merchant_id=merchant.id,
                        source_id=source_id,
                        event_type=event_type,
                        payload=_payload_for(event, event_type),
                        now=now,
                    )
                )
            uow.commit()


# ============================================================== livraison (job)
@dataclass(frozen=True, slots=True)
class WebhookSendResult:
    ok: bool
    status_code: int | None = None
    error: str | None = None


@runtime_checkable
class MerchantWebhookSender(Protocol):
    def send(
        self, *, url: str, secret: str, event_type: str, delivery_id: str, body: bytes
    ) -> WebhookSendResult: ...


@dataclass(frozen=True, slots=True)
class MerchantWebhookReport:
    due: int
    delivered: int
    retried: int
    exhausted: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "due": self.due,
            "delivered": self.delivered,
            "retried": self.retried,
            "exhausted": self.exhausted,
        }


class DispatchMerchantWebhooks:
    def __init__(self, *, services: AppServices, sender: MerchantWebhookSender) -> None:
        self._services = services
        self._sender = sender

    def execute(self) -> MerchantWebhookReport:
        now = self._services.clock.now()
        counts = {"due": 0, "delivered": 0, "retried": 0, "exhausted": 0}

        def work(uow: WorkUnitOfWork) -> None:
            for delivery in uow.merchant_webhooks.list_due(now):
                counts["due"] += 1
                merchant = uow.merchants.get(delivery.merchant_id)
                if merchant is None or not merchant.has_webhook:
                    delivery.record_failure(error="Webhook non configuré.", now=now)
                else:
                    body = json.dumps(
                        delivery.payload, sort_keys=True, separators=(",", ":")
                    ).encode()
                    result = self._sender.send(
                        url=merchant.webhook_url or "",
                        secret=merchant.webhook_secret or "",
                        event_type=delivery.event_type,
                        delivery_id=str(delivery.id),
                        body=body,
                    )
                    if result.ok:
                        delivery.record_success(now)
                    else:
                        delivery.record_failure(
                            error=result.error or f"HTTP {result.status_code}", now=now
                        )
                uow.merchant_webhooks.save(delivery)
                if delivery.status.value == "DELIVERED":
                    counts["delivered"] += 1
                elif delivery.status.value == "FAILED":
                    counts["exhausted"] += 1
                else:
                    counts["retried"] += 1

        execute_in_uow(self._services.uow, self._services.events, work)
        return MerchantWebhookReport(
            due=counts["due"],
            delivered=counts["delivered"],
            retried=counts["retried"],
            exhausted=counts["exhausted"],
        )


__all__ = [
    "ClearMerchantWebhook",
    "ClearMerchantWebhookCommand",
    "ConfigureMerchantWebhook",
    "ConfigureMerchantWebhookCommand",
    "DispatchMerchantWebhooks",
    "MerchantWebhookEnqueuer",
    "MerchantWebhookReport",
    "MerchantWebhookSender",
    "MerchantWebhookView",
    "WebhookSendResult",
]
