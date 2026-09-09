"""Tests des blueprints interop opérateurs + webhook signé (BE-065 → BE-067)."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient

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
OP_SECRET = "test-operator-webhook-secret"
PHONE = "+2250700000001"
TARGET = "+2250712345678"


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


def _login(client: FlaskClient, key: str) -> dict[str, str]:
    client.post(
        "/v1/auth/register",
        json={"phone_number": PHONE, "pin": "1397", "country": "CI"},
        headers={"Idempotency-Key": key},
    )
    tokens = client.post(
        "/v1/auth/verify-otp",
        json={"phone_number": PHONE, "country": "CI", "code": "000000", "device_id": "d1"},
    ).get_json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _fund(uow: InMemoryUnitOfWork, amount: int) -> None:
    user = uow.users.get_by_msisdn(Msisdn(PHONE))
    assert user is not None
    wallet = uow.wallets.list_for_user(user.id)[0]
    wallet.credit(Money(amount, XOF), FixedClock().now())
    wallet.pull_events()


def _signed(client: FlaskClient, path: str, payload: dict[str, Any]) -> Any:
    body = json.dumps(payload).encode()
    sig = hmac.new(OP_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        path, data=body, content_type="application/json", headers={"X-Operator-Signature": sig}
    )


class TestPayoutFlow:
    def test_payout_then_success_callback_settles(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, uow, _deps = app_and_uow
        client = app.test_client()
        auth = _login(client, "op-setup-1")
        _fund(uow, 100_000)

        resp = client.post(
            "/v1/operators/payouts",
            headers={**auth, "Idempotency-Key": "op-payout-1"},
            json={"operator": "ORANGE_CI", "msisdn": TARGET, "amount_minor": 50_000},
        )
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["status"] == "PENDING" and body["fee_minor"] == 750
        reference = body["reference"]

        wallet = client.get("/v1/wallets", headers=auth).get_json()["wallets"][0]
        assert wallet["available_minor"] == 100_000 - 50_750
        assert wallet["reserved_minor"] == 50_750

        cb = _signed(
            client,
            "/v1/operators/ORANGE_CI/callbacks",
            {"reference": reference, "status": "SUCCEEDED", "external_ref": "op_ext_1"},
        )
        assert cb.status_code == 200 and cb.get_json()["status"] == "SUCCEEDED"

        wallet = client.get("/v1/wallets", headers=auth).get_json()["wallets"][0]
        assert wallet["reserved_minor"] == 0 and wallet["balance_minor"] == 49_250

        transfers = client.get("/v1/operators/transfers", headers=auth).get_json()["transfers"]
        assert transfers[0]["status"] == "SUCCEEDED"

    def test_failure_callback_restores_funds(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, uow, _deps = app_and_uow
        client = app.test_client()
        auth = _login(client, "op-setup-2")
        _fund(uow, 100_000)
        reference = client.post(
            "/v1/operators/payouts",
            headers={**auth, "Idempotency-Key": "op-payout-2"},
            json={"operator": "ORANGE_CI", "msisdn": TARGET, "amount_minor": 50_000},
        ).get_json()["reference"]

        _signed(
            client,
            "/v1/operators/ORANGE_CI/callbacks",
            {"reference": reference, "status": "FAILED", "reason": "OPERATOR_DOWN"},
        )
        wallet = client.get("/v1/wallets", headers=auth).get_json()["wallets"][0]
        assert wallet["available_minor"] == 100_000 and wallet["reserved_minor"] == 0

    def test_payout_requires_idempotency_key(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, uow, _deps = app_and_uow
        client = app.test_client()
        auth = _login(client, "op-setup-3")
        _fund(uow, 100_000)
        resp = client.post(
            "/v1/operators/payouts",
            headers=auth,
            json={"operator": "ORANGE_CI", "msisdn": TARGET, "amount_minor": 1_000},
        )
        assert resp.status_code == 400


class TestTopUpFlow:
    def test_topup_then_success_callback_credits(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, uow, _deps = app_and_uow
        client = app.test_client()
        auth = _login(client, "op-setup-4")
        _fund(uow, 1_000)

        reference = client.post(
            "/v1/operators/topups",
            headers={**auth, "Idempotency-Key": "op-topup-1"},
            json={"operator": "MTN_CI", "msisdn": TARGET, "amount_minor": 30_000},
        ).get_json()["reference"]

        _signed(
            client,
            "/v1/operators/MTN_CI/callbacks",
            {"reference": reference, "status": "SUCCEEDED"},
        )
        wallet = client.get("/v1/wallets", headers=auth).get_json()["wallets"][0]
        assert wallet["available_minor"] == 1_000 + 30_000 - 300


class TestWebhookSecurity:
    def test_bad_signature_is_401(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, _uow, _deps = app_and_uow
        client = app.test_client()
        resp = client.post(
            "/v1/operators/ORANGE_CI/callbacks",
            json={"reference": "OPO-x", "status": "SUCCEEDED"},
            headers={"X-Operator-Signature": "deadbeef"},
        )
        assert resp.status_code == 401

    def test_unknown_reference_is_422(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, _uow, _deps = app_and_uow
        client = app.test_client()
        resp = _signed(
            client,
            "/v1/operators/ORANGE_CI/callbacks",
            {"reference": "OPO-missing", "status": "SUCCEEDED"},
        )
        assert resp.status_code == 422

    def test_requires_auth(self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]) -> None:
        app, _uow, _deps = app_and_uow
        assert app.test_client().get("/v1/operators/transfers").status_code == 401
