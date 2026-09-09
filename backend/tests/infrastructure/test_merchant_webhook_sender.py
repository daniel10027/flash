"""``HttpMerchantWebhookSender`` (BE-071) : signature + robustesse réseau."""

from __future__ import annotations

import hashlib
import hmac

from flash.infrastructure.merchant_webhooks import HttpMerchantWebhookSender, sign


def test_sign_is_hmac_sha256_hex_with_prefix() -> None:
    body = b'{"a":1}'
    expected = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert sign("secret", body) == expected


def test_sign_changes_with_secret_and_body() -> None:
    assert sign("s1", b"x") != sign("s2", b"x")
    assert sign("s", b"x") != sign("s", b"y")


def test_send_to_unroutable_host_fails_gracefully() -> None:
    sender = HttpMerchantWebhookSender(timeout=1)
    result = sender.send(
        url="http://127.0.0.1:0/hook",
        secret="a-sixteen-char-secret!",
        event_type="payment.completed",
        delivery_id="d1",
        body=b"{}",
    )
    assert result.ok is False
    assert result.error is not None
