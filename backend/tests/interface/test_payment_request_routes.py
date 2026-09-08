"""Tests du blueprint payment_requests : créer / accepter / refuser / annuler (BE-032)."""

from __future__ import annotations

from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient

from flash.infrastructure.config import Settings
from flash.interface.app import create_app
from tests.support.deps import build_test_deps
from tests.support.otp import RecordingOtpService
from tests.support.repositories import InMemoryUnitOfWork
from tests.support.security import build_test_security

SECRET = "flash-test-secret-please-ignore-0123456789abcd"
REQUESTER = "+2250700000001"
PAYER = "+2250700000002"


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


@pytest.fixture
def app(uow: InMemoryUnitOfWork) -> Flask:
    bundle = build_test_security()
    deps = build_test_deps(uow=uow, otp=RecordingOtpService(), bundle=bundle)
    return create_app(
        Settings(FLASH_ENV="test", FLASH_SECRET_KEY=SECRET),
        security_bundle=bundle,
        deps=deps,
    )


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()


def _register(client: FlaskClient, phone: str, key: str) -> dict[str, str]:
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


@pytest.fixture
def requester_auth(client: FlaskClient) -> dict[str, str]:
    return _register(client, REQUESTER, "prq-setup-requester")


@pytest.fixture
def payer_auth(client: FlaskClient) -> dict[str, str]:
    # Le payeur n'est pas crédité ici : ces tests vérifient le câblage HTTP et les gardes ;
    # le déplacement d'argent à l'acceptation est couvert par les tests applicatifs.
    return _register(client, PAYER, "prq-setup-payer")


def _create(client: FlaskClient, auth: dict[str, str], key: str = "prq-http-1") -> dict[str, Any]:
    body: dict[str, Any] = client.post(
        "/v1/payment-requests",
        headers={**auth, "Idempotency-Key": key},
        json={"payer_phone_number": PAYER, "amount_minor": 12_000, "note": "Ciné"},
    ).get_json()
    return body


class TestPaymentRequestEndpoints:
    def test_requires_auth(self, client: FlaskClient) -> None:
        assert client.get("/v1/payment-requests").status_code == 401

    def test_create_requires_idempotency_key(
        self, client: FlaskClient, requester_auth: dict[str, str], payer_auth: dict[str, str]
    ) -> None:
        resp = client.post(
            "/v1/payment-requests",
            headers=requester_auth,
            json={"payer_phone_number": PAYER, "amount_minor": 12_000},
        )
        assert resp.status_code == 400

    def test_create_then_appears_in_both_boxes(
        self, client: FlaskClient, requester_auth: dict[str, str], payer_auth: dict[str, str]
    ) -> None:
        created = _create(client, requester_auth)
        assert created["status"] == "PENDING"
        rid = created["request_id"]

        outgoing = client.get(
            "/v1/payment-requests?box=outgoing", headers=requester_auth
        ).get_json()
        incoming = client.get("/v1/payment-requests?box=incoming", headers=payer_auth).get_json()
        assert [r["request_id"] for r in outgoing["requests"]] == [rid]
        assert [r["request_id"] for r in incoming["requests"]] == [rid]

    def test_decline_by_payer(
        self, client: FlaskClient, requester_auth: dict[str, str], payer_auth: dict[str, str]
    ) -> None:
        rid = _create(client, requester_auth)["request_id"]
        resp = client.post(f"/v1/payment-requests/{rid}/decline", headers=payer_auth)
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "DECLINED"

    def test_cancel_by_requester(
        self, client: FlaskClient, requester_auth: dict[str, str], payer_auth: dict[str, str]
    ) -> None:
        rid = _create(client, requester_auth)["request_id"]
        resp = client.post(f"/v1/payment-requests/{rid}/cancel", headers=requester_auth)
        assert resp.status_code == 204

    def test_accept_without_funds_is_422(
        self, client: FlaskClient, requester_auth: dict[str, str], payer_auth: dict[str, str]
    ) -> None:
        rid = _create(client, requester_auth)["request_id"]
        resp = client.post(f"/v1/payment-requests/{rid}/accept", headers=payer_auth)
        assert resp.status_code == 422
        assert resp.get_json()["code"] == "INSUFFICIENT_FUNDS"

    def test_cancel_someone_elses_request_is_422(
        self, client: FlaskClient, requester_auth: dict[str, str], payer_auth: dict[str, str]
    ) -> None:
        rid = _create(client, requester_auth)["request_id"]
        resp = client.post(f"/v1/payment-requests/{rid}/cancel", headers=payer_auth)
        assert resp.status_code == 422
