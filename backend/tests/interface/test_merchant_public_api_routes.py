"""Routes BE-071 : API marchande publique /merchant/v1 + config webhook + job de livraison."""

from __future__ import annotations

from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient

from flash.application.merchants.kyb import ReviewMerchantKyb, ReviewMerchantKybCommand
from flash.application.merchants.operations import EnrollMerchant, EnrollMerchantCommand
from flash.domain.shared.identifiers import Msisdn
from flash.domain.shared.money import XOF, Money
from flash.infrastructure.config import Settings
from flash.interface.app import create_app
from tests.support.deps import build_test_deps
from tests.support.fakes import FixedClock
from tests.support.otp import RecordingOtpService
from tests.support.repositories import InMemoryUnitOfWork
from tests.support.security import build_test_security
from tests.support.webhooks import RecordingMerchantWebhookSender

SECRET = "flash-test-secret-please-ignore-0123456789abcd"
ADMIN_KEY = "test-admin-key"
MERCHANT_PHONE = "+2250700000009"
PAYER_PHONE = "+2250700000001"
WEBHOOK_SECRET = "merchant-webhook-secret-32chars!!"


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


@pytest.fixture
def app_and_uow(uow: InMemoryUnitOfWork) -> tuple[Flask, InMemoryUnitOfWork, Any]:
    bundle = build_test_security()
    deps = build_test_deps(uow=uow, otp=RecordingOtpService(), bundle=bundle)
    app = create_app(
        Settings(FLASH_ENV="test", FLASH_SECRET_KEY=SECRET),
        security_bundle=bundle,
        deps=deps,
    )
    return app, uow, deps


def _login(client: FlaskClient, phone: str, key: str) -> dict[str, str]:
    client.post(
        "/v1/auth/register",
        json={"phone_number": phone, "pin": "1397", "country": "CI"},
        headers={"Idempotency-Key": key},
    )
    tokens = client.post(
        "/v1/auth/verify-otp",
        json={"phone_number": phone, "country": "CI", "code": "000000", "device_id": "d1"},
    ).get_json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _bootstrap(
    app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any],
) -> tuple[FlaskClient, dict[str, str], dict[str, str], str]:
    app, uow, deps = app_and_uow
    client = app.test_client()
    merchant_auth = _login(client, MERCHANT_PHONE, "merchant-public-api-setup")
    payer_auth = _login(client, PAYER_PHONE, "payer-public-api-setup")

    payer = uow.users.get_by_msisdn(Msisdn(PAYER_PHONE))
    assert payer is not None
    wallet = uow.wallets.list_for_user(payer.id)[0]
    wallet.credit(Money(100_000, XOF), FixedClock().now())
    wallet.pull_events()

    merchant_user = uow.users.get_by_msisdn(Msisdn(MERCHANT_PHONE))
    assert merchant_user is not None
    view = EnrollMerchant(services=deps.services).execute(
        EnrollMerchantCommand(user_id=str(merchant_user.id), display_name="Chez Awa")
    )
    ReviewMerchantKyb(services=deps.services).execute(
        ReviewMerchantKybCommand(merchant_id=view.merchant_id, reviewer="key:admin", approve=True)
    )
    issued = client.post(
        "/v1/merchant/api-keys", headers=merchant_auth, json={"label": "prod"}
    ).get_json()
    return client, merchant_auth, payer_auth, issued["secret"]


class TestPublicApi:
    def test_full_charge_pay_status_refund_flow(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        client, _merchant_auth, payer_auth, api_secret = _bootstrap(app_and_uow)
        api = {"Authorization": f"Bearer {api_secret}"}

        charge = client.post(
            "/merchant/v1/charges",
            headers=api,
            json={"amount_minor": 25_000, "reference": "Commande 42"},
        )
        assert charge.status_code == 201
        charge_id = charge.get_json()["charge_id"]

        status = client.get(f"/merchant/v1/charges/{charge_id}", headers=api).get_json()
        assert status["status"] == "PENDING" and status["payment_id"] is None

        paid = client.post(
            "/v1/merchant-payments",
            headers={**payer_auth, "Idempotency-Key": "public-api-pay-1"},
            json={"merchant_id": status["merchant_id"], "charge_id": charge_id},
        )
        assert paid.status_code == 201

        status2 = client.get(f"/merchant/v1/charges/{charge_id}", headers=api).get_json()
        assert status2["status"] == "PAID" and status2["payment_id"] is not None

        payments = client.get("/merchant/v1/payments", headers=api).get_json()
        assert len(payments["payments"]) == 1

        refund = client.post(
            f"/merchant/v1/charges/{charge_id}/refund",
            headers={**api, "Idempotency-Key": "public-api-refund-1"},
        )
        assert refund.status_code == 200
        assert refund.get_json()["status"] == "REFUNDED"

    def test_missing_key_is_401(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, _uow, _deps = app_and_uow
        resp = app.test_client().post(
            "/merchant/v1/charges", json={"amount_minor": 1000, "reference": "x"}
        )
        assert resp.status_code == 401

    def test_bad_key_is_401(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        client, *_ = _bootstrap(app_and_uow)
        resp = client.get(
            "/merchant/v1/payments", headers={"X-Merchant-Key": "mk_deadbeef_" + "z" * 32}
        )
        assert resp.status_code == 401

    def test_refund_without_payment_is_422(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        client, _merchant_auth, _payer_auth, api_secret = _bootstrap(app_and_uow)
        api = {"Authorization": f"Bearer {api_secret}"}
        charge_id = client.post(
            "/merchant/v1/charges",
            headers=api,
            json={"amount_minor": 25_000, "reference": "x"},
        ).get_json()["charge_id"]
        resp = client.post(
            f"/merchant/v1/charges/{charge_id}/refund",
            headers={**api, "Idempotency-Key": "no-payment-refund"},
        )
        assert resp.status_code == 422

    def test_key_stops_working_after_revoke(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        client, merchant_auth, _payer_auth, api_secret = _bootstrap(app_and_uow)
        api = {"Authorization": f"Bearer {api_secret}"}
        keys = client.get("/v1/merchant/api-keys", headers=merchant_auth).get_json()
        key_id = keys["api_keys"][0]["key_id"]
        client.delete(f"/v1/merchant/api-keys/{key_id}", headers=merchant_auth)
        assert client.get("/merchant/v1/payments", headers=api).status_code == 401


class TestWebhookConfigAndJob:
    def test_configure_then_dispatch_delivers_signed_webhook(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        _app, _uow, deps = app_and_uow
        sender = RecordingMerchantWebhookSender()
        object.__setattr__(deps, "merchant_webhook_sender", sender)

        client, merchant_auth, payer_auth, api_secret = _bootstrap(app_and_uow)
        api = {"Authorization": f"Bearer {api_secret}"}

        cfg = client.put(
            "/v1/merchant/webhook",
            headers=merchant_auth,
            json={"url": "https://shop.example.com/hook", "secret": WEBHOOK_SECRET},
        )
        assert cfg.status_code == 200 and cfg.get_json()["configured"] is True

        charge_id = client.post(
            "/merchant/v1/charges",
            headers=api,
            json={"amount_minor": 25_000, "reference": "Commande 42"},
        ).get_json()["charge_id"]
        status = client.get(f"/merchant/v1/charges/{charge_id}", headers=api).get_json()
        client.post(
            "/v1/merchant-payments",
            headers={**payer_auth, "Idempotency-Key": "webhook-pay-1"},
            json={"merchant_id": status["merchant_id"], "charge_id": charge_id},
        )

        run = client.post(
            "/v1/admin/jobs/merchants/webhooks", headers={"X-Admin-Key": ADMIN_KEY}
        )
        assert run.status_code == 200
        body = run.get_json()
        assert body["delivered"] == 1
        assert sender.calls[0]["url"] == "https://shop.example.com/hook"

    def test_webhook_job_requires_admin(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, _uow, _deps = app_and_uow
        assert (
            app.test_client().post("/v1/admin/jobs/merchants/webhooks").status_code == 403
        )

    def test_clear_webhook(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        client, merchant_auth, _payer_auth, _api = _bootstrap(app_and_uow)
        client.put(
            "/v1/merchant/webhook",
            headers=merchant_auth,
            json={"url": "https://shop.example.com/hook", "secret": WEBHOOK_SECRET},
        )
        resp = client.delete("/v1/merchant/webhook", headers=merchant_auth)
        assert resp.status_code == 200 and resp.get_json()["configured"] is False

    def test_configure_webhook_rejects_short_secret(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        client, merchant_auth, _payer_auth, _api = _bootstrap(app_and_uow)
        resp = client.put(
            "/v1/merchant/webhook",
            headers=merchant_auth,
            json={"url": "https://shop.example.com/hook", "secret": "short"},
        )
        assert resp.status_code == 422
