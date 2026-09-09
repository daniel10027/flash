"""``HttpMerchantWebhookSender`` — implémentation du port ``MerchantWebhookSender``.

POST le corps JSON tel quel sur l'URL du marchand, avec les en-têtes :
- ``Content-Type: application/json``
- ``X-Flash-Event: <event_type>``
- ``X-Flash-Delivery: <delivery_id>``
- ``X-Flash-Signature: sha256=<hmac_hex(secret, body)>``

Un code 2xx = succès. Toute autre réponse, timeout ou erreur réseau = échec (le job
re-tentera). ``timeout`` court pour ne pas bloquer le job.
"""

from __future__ import annotations

import hashlib
import hmac
import urllib.error
import urllib.request

from flash.application.merchants.webhooks import MerchantWebhookSender, WebhookSendResult

_TIMEOUT_SECONDS = 5


def sign(secret: str, body: bytes) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class HttpMerchantWebhookSender(MerchantWebhookSender):
    def __init__(self, *, timeout: int = _TIMEOUT_SECONDS) -> None:
        self._timeout = timeout

    def send(
        self, *, url: str, secret: str, event_type: str, delivery_id: str, body: bytes
    ) -> WebhookSendResult:
        request = urllib.request.Request(
            url,
            data=body,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "X-Flash-Event": event_type,
                "X-Flash-Delivery": delivery_id,
                "X-Flash-Signature": sign(secret, body),
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=self._timeout) as resp:
                code = resp.getcode()
        except urllib.error.HTTPError as exc:
            return WebhookSendResult(ok=False, status_code=exc.code, error=f"HTTP {exc.code}")
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            return WebhookSendResult(ok=False, error=f"{type(exc).__name__}: {exc}")
        ok = 200 <= code < 300
        return WebhookSendResult(ok=ok, status_code=code, error=None if ok else f"HTTP {code}")


__all__ = ["HttpMerchantWebhookSender", "sign"]
