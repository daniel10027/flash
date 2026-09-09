"""Tests des routes de règlement marchand (BE-070) : configuration, déclenchement,
historique, relevé, et le job back-office."""

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
ADMIN_KEY = "test-admin-key"
MERCHANT_PHONE = "+2250700000009"
PAYER_PHONE = "+2250700000001"
IBAN = "CI93 CI00 8011 3011 3429 1200 589"


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


def _setup(
    app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any], *, tag: str
) -> tuple[FlaskClient, dict[str, str], dict[str, str], str]:
    app, uow, deps = app_and_uow
    client = app.test_client()
    merchant_auth = _login(client, MERCHANT_PHONE, f"merchant-setup-{tag}")
    payer_auth = _login(client, PAYER_PHONE, f"payer-setup-{tag}")

    payer_user = uow.users.get_by_msisdn(Msisdn(PAYER_PHONE))
    assert payer_user is not None
    payer_wallet = uow.wallets.list_for_user(payer_user.id)[0]
    payer_wallet.credit(Money(100_000, XOF), FixedClock().now())
    payer_wallet.pull_events()

    merchant_user = uow.users.get_by_msisdn(Msisdn(MERCHANT_PHONE))
    assert merchant_user is not None
    merchant_view = EnrollMerchant(services=deps.services).execute(
        EnrollMerchantCommand(user_id=str(merchant_user.id), display_name="Chez Awa")
    )
    return client, merchant_auth, payer_auth, merchant_view.merchant_id


def _pay(client: FlaskClient, payer_auth: dict[str, str], merchant_id: str, key: str) -> None:
    resp = client.post(
        "/v1/merchant-payments",
        headers={**payer_auth, "Idempotency-Key": key},
        json={"merchant_id": merchant_id, "amount_minor": 25_000},
    )
    assert resp.status_code == 201


class TestSettlementRoutes:
    def test_configure_then_settle_then_statement(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        client, merchant_auth, payer_auth, merchant_id = _setup(app_and_uow, tag="flow")
        _pay(client, payer_auth, merchant_id, "pay-settlement-0001")

        cfg = client.put(
            "/v1/merchant/settlement",
            headers=merchant_auth,
            json={
                "holder": "SARL Chez Awa",
                "iban": IBAN,
                "bank_name": "Ecobank CI",
                "frequency": "WEEKLY",
            },
        )
        assert cfg.status_code == 200
        assert cfg.get_json()["bank_iban_masked"].startswith("CI93")

        settle = client.post("/v1/merchant/settlements", headers=merchant_auth)
        assert settle.status_code == 200
        body = settle.get_json()["settlement"]
        assert body["status"] == "PAID"
        assert body["amount_minor"] == 25_000 - 250

        hist = client.get("/v1/merchant/settlements", headers=merchant_auth).get_json()
        assert len(hist["settlements"]) == 1
        sid = hist["settlements"][0]["settlement_id"]

        statement = client.get(
            f"/v1/merchant/settlements/{sid}", headers=merchant_auth
        ).get_json()
        assert statement["settlement"]["settlement_id"] == sid
        assert statement["lines"][0]["net_minor"] == 24_750

    def test_settle_without_encours_returns_detail(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        client, merchant_auth, _payer_auth, _merchant_id = _setup(app_and_uow, tag="empty")
        client.put(
            "/v1/merchant/settlement",
            headers=merchant_auth,
            json={"holder": "Awa", "iban": IBAN, "bank_name": "Ecobank"},
        )
        resp = client.post("/v1/merchant/settlements", headers=merchant_auth)
        assert resp.status_code == 200
        assert resp.get_json()["settlement"] is None

    def test_settle_without_bank_account_is_422(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        client, merchant_auth, _payer_auth, _merchant_id = _setup(app_and_uow, tag="nobank")
        resp = client.post("/v1/merchant/settlements", headers=merchant_auth)
        assert resp.status_code == 422

    def test_configure_rejects_bad_iban(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        client, merchant_auth, _payer_auth, _merchant_id = _setup(app_and_uow, tag="badiban")
        resp = client.put(
            "/v1/merchant/settlement",
            headers=merchant_auth,
            json={"holder": "Awa", "iban": "x", "bank_name": "Ecobank"},
        )
        assert resp.status_code == 422

    def test_routes_require_auth(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, _uow, _deps = app_and_uow
        client = app.test_client()
        assert client.get("/v1/merchant/settlements").status_code == 401
        assert client.put("/v1/merchant/settlement", json={}).status_code == 401

    def test_statement_unknown_id_is_422(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        client, merchant_auth, _payer_auth, _merchant_id = _setup(app_and_uow, tag="unknown")
        resp = client.get(
            "/v1/merchant/settlements/00000000-0000-4000-8000-000000000123",
            headers=merchant_auth,
        )
        assert resp.status_code == 422


class TestAdminSettleJob:
    def test_admin_job_settles_due_merchants(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        client, merchant_auth, payer_auth, merchant_id = _setup(app_and_uow, tag="job")
        _pay(client, payer_auth, merchant_id, "pay-job-settlement-1")
        client.put(
            "/v1/merchant/settlement",
            headers=merchant_auth,
            json={
                "holder": "Awa",
                "iban": IBAN,
                "bank_name": "Ecobank",
                "frequency": "DAILY",
            },
        )
        _app, _uow, deps = app_and_uow
        deps.services.clock.advance(days=1)

        resp = client.post(
            "/v1/admin/jobs/merchants/settle", headers={"X-Admin-Key": ADMIN_KEY}
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["checked"] == 1 and body["settled"] == 1
        assert body["settled_minor"] == 25_000 - 250

    def test_admin_job_requires_admin_key(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, _uow, _deps = app_and_uow
        resp = app.test_client().post("/v1/admin/jobs/merchants/settle")
        assert resp.status_code == 403
