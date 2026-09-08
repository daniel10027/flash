"""Tests des blueprints marchands : QR, charges, paiement (BE-033)."""

from __future__ import annotations

from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient

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

SECRET = "flash-test-secret-please-ignore-0123456789abcd"
MERCHANT_PHONE = "+2250700000009"
PAYER_PHONE = "+2250700000001"


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


class TestMerchantEndpoints:
    def test_full_static_qr_payment_flow(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, uow, deps = app_and_uow
        client = app.test_client()
        merchant_auth = _login(client, MERCHANT_PHONE, "m-setup-key")
        payer_auth = _login(client, PAYER_PHONE, "p-setup-key")

        # créditer le payeur directement dans le registre in-memory
        payer_wallet = uow.wallets.list_for_user(
            uow.users.get_by_msisdn(Msisdn(PAYER_PHONE)).id  # type: ignore[union-attr]
        )[0]
        payer_wallet.credit(Money(100_000, XOF), FixedClock().now())
        payer_wallet.pull_events()

        merchant_user = uow.users.get_by_msisdn(Msisdn(MERCHANT_PHONE))
        assert merchant_user is not None
        merchant_view = EnrollMerchant(services=deps.services).execute(
            EnrollMerchantCommand(user_id=str(merchant_user.id), display_name="Chez Awa")
        )

        qr = client.get("/v1/merchant/qr", headers=merchant_auth).get_json()
        assert qr["static_qr_payload"].endswith(merchant_view.merchant_id)

        resp = client.post(
            "/v1/merchant-payments",
            headers={**payer_auth, "Idempotency-Key": "pay-key-0001"},
            json={"merchant_id": merchant_view.merchant_id, "amount_minor": 25_000},
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["fee_minor"] == 250
        assert body["payer_balance_after_minor"] == 75_000

        received = client.get("/v1/merchant/payments", headers=merchant_auth).get_json()
        assert [p["amount_minor"] for p in received["payments"]] == [25_000]

    def test_dynamic_charge_then_pay(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, uow, deps = app_and_uow
        client = app.test_client()
        merchant_auth = _login(client, MERCHANT_PHONE, "m-setup2")
        payer_auth = _login(client, PAYER_PHONE, "p-setup2")

        payer_wallet = uow.wallets.list_for_user(
            uow.users.get_by_msisdn(Msisdn(PAYER_PHONE)).id  # type: ignore[union-attr]
        )[0]
        payer_wallet.credit(Money(100_000, XOF), FixedClock().now())
        payer_wallet.pull_events()

        merchant_user = uow.users.get_by_msisdn(Msisdn(MERCHANT_PHONE))
        assert merchant_user is not None
        EnrollMerchant(services=deps.services).execute(
            EnrollMerchantCommand(user_id=str(merchant_user.id), display_name="Chez Awa")
        )

        charge = client.post(
            "/v1/merchant/charges",
            headers={**merchant_auth, "Idempotency-Key": "charge-key-1"},
            json={"amount_minor": 30_000, "reference": "Table 7"},
        ).get_json()
        assert charge["status"] == "PENDING"

        resp = client.post(
            "/v1/merchant-payments",
            headers={**payer_auth, "Idempotency-Key": "pay-dyn-key-1"},
            json={"merchant_id": charge["merchant_id"], "charge_id": charge["charge_id"]},
        )
        assert resp.status_code == 201
        assert resp.get_json()["amount_minor"] == 30_000

    def test_refund_credits_payer_back(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, uow, deps = app_and_uow
        client = app.test_client()
        merchant_auth = _login(client, MERCHANT_PHONE, "m-setup-rf")
        payer_auth = _login(client, PAYER_PHONE, "p-setup-rf")

        payer_wallet = uow.wallets.list_for_user(
            uow.users.get_by_msisdn(Msisdn(PAYER_PHONE)).id  # type: ignore[union-attr]
        )[0]
        payer_wallet.credit(Money(100_000, XOF), FixedClock().now())
        payer_wallet.pull_events()

        merchant_user = uow.users.get_by_msisdn(Msisdn(MERCHANT_PHONE))
        assert merchant_user is not None
        merchant_view = EnrollMerchant(services=deps.services).execute(
            EnrollMerchantCommand(user_id=str(merchant_user.id), display_name="Chez Awa")
        )
        payment = client.post(
            "/v1/merchant-payments",
            headers={**payer_auth, "Idempotency-Key": "pay-rf-0001"},
            json={"merchant_id": merchant_view.merchant_id, "amount_minor": 25_000},
        ).get_json()

        resp = client.post(
            f"/v1/merchant/payments/{payment['payment_id']}/refund",
            headers={**merchant_auth, "Idempotency-Key": "refund-rf-0001"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "REFUNDED"

        bal = client.get("/v1/wallets", headers=payer_auth).get_json()["wallets"][0]
        assert bal["balance_minor"] == 100_000

    def test_qr_for_non_merchant_is_404(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, _uow, _deps = app_and_uow
        client = app.test_client()
        auth = _login(client, PAYER_PHONE, "p-setup3")
        assert client.get("/v1/merchant/qr", headers=auth).status_code == 404

    def test_pay_requires_idempotency_key(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, _uow, _deps = app_and_uow
        client = app.test_client()
        auth = _login(client, PAYER_PHONE, "p-setup4")
        resp = client.post(
            "/v1/merchant-payments",
            headers=auth,
            json={"merchant_id": "00000000-0000-4000-8000-000000000000", "amount_minor": 1_000},
        )
        assert resp.status_code == 400

    def test_requires_auth(self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]) -> None:
        app, _uow, _deps = app_and_uow
        assert app.test_client().get("/v1/merchant/qr").status_code == 401
