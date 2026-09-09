"""Envoyeur de webhooks marchand contrôlé pour les tests."""

from __future__ import annotations

from dataclasses import dataclass, field

from flash.application.merchants.webhooks import WebhookSendResult


@dataclass
class RecordingMerchantWebhookSender:
    """Mémorise les envois. ``fail_until`` fait échouer les N premiers appels."""

    fail_until: int = 0
    boom: bool = False
    calls: list[dict[str, object]] = field(default_factory=list)

    def send(
        self, *, url: str, secret: str, event_type: str, delivery_id: str, body: bytes
    ) -> WebhookSendResult:
        self.calls.append(
            {
                "url": url,
                "secret": secret,
                "event_type": event_type,
                "delivery_id": delivery_id,
                "body": body,
            }
        )
        if self.boom:
            raise RuntimeError("sender exploded")
        if len(self.calls) <= self.fail_until:
            return WebhookSendResult(ok=False, status_code=503, error="HTTP 503")
        return WebhookSendResult(ok=True, status_code=200)


__all__ = ["RecordingMerchantWebhookSender"]
