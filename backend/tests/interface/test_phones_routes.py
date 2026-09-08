"""Tests du blueprint phones : add / verify / list / remove / primary (BE-028)."""

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
PRIMARY = "+2250700000001"


@pytest.fixture
def otp() -> RecordingOtpService:
    return RecordingOtpService()


@pytest.fixture
def app(otp: RecordingOtpService) -> Flask:
    bundle = build_test_security()
    deps = build_test_deps(uow=InMemoryUnitOfWork(), otp=otp, bundle=bundle)
    return create_app(
        Settings(FLASH_ENV="test", FLASH_SECRET_KEY=SECRET),
        security_bundle=bundle,
        deps=deps,
    )


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()


@pytest.fixture
def auth(client: FlaskClient) -> dict[str, str]:
    """Crée un compte activé et renvoie l'en-tête Authorization."""
    client.post(
        "/v1/auth/register",
        json={"phone_number": PRIMARY, "pin": "1397", "country": "CI"},
        headers={"Idempotency-Key": "phones-setup-key"},
    )
    tokens = client.post(
        "/v1/auth/verify-otp",
        json={"phone_number": PRIMARY, "country": "CI", "code": "000000", "device_id": "d1"},
    ).get_json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _list(client: FlaskClient, auth: dict[str, str]) -> list[dict[str, Any]]:
    return list(client.get("/v1/phones", headers=auth).get_json()["phone_numbers"])


class TestPhonesEndpoints:
    def test_requires_authentication(self, client: FlaskClient) -> None:
        assert client.get("/v1/phones").status_code == 401

    def test_list_starts_with_verified_primary(
        self, client: FlaskClient, auth: dict[str, str]
    ) -> None:
        phones = _list(client, auth)
        assert len(phones) == 1
        assert phones[0]["is_primary"] and phones[0]["is_verified"]
        assert phones[0]["masked"].startswith("+225")

    def test_add_then_verify_then_promote(self, client: FlaskClient, auth: dict[str, str]) -> None:
        new = "+2250700000002"
        added = client.post("/v1/phones", json={"phone_number": new, "country": "CI"}, headers=auth)
        assert added.status_code == 202
        assert added.get_json()["verification_required"] is True
        assert any(not p["is_verified"] for p in _list(client, auth))

        verified = client.post(
            "/v1/phones/verify",
            json={"phone_number": new, "country": "CI", "code": "000000"},
            headers=auth,
        )
        assert verified.status_code == 200
        assert verified.get_json()["is_verified"] is True

        promoted = client.post(
            "/v1/phones/primary", json={"phone_number": new, "country": "CI"}, headers=auth
        )
        assert promoted.status_code == 200
        primaries = [p for p in promoted.get_json()["phone_numbers"] if p["is_primary"]]
        assert len(primaries) == 1 and primaries[0]["phone_number"] == new

    def test_promote_unverified_is_422(self, client: FlaskClient, auth: dict[str, str]) -> None:
        client.post(
            "/v1/phones", json={"phone_number": "+2250700000002", "country": "CI"}, headers=auth
        )
        resp = client.post(
            "/v1/phones/primary",
            json={"phone_number": "+2250700000002", "country": "CI"},
            headers=auth,
        )
        assert resp.status_code == 422
        assert resp.get_json()["code"] == "PHONE_NUMBER_NOT_VERIFIED"

    def test_remove_secondary_then_list_shrinks(
        self, client: FlaskClient, auth: dict[str, str]
    ) -> None:
        client.post(
            "/v1/phones", json={"phone_number": "+2250700000002", "country": "CI"}, headers=auth
        )
        resp = client.delete(
            "/v1/phones", json={"phone_number": "+2250700000002", "country": "CI"}, headers=auth
        )
        assert resp.status_code == 204
        assert [p["phone_number"] for p in _list(client, auth)] == [PRIMARY]

    def test_remove_primary_is_409(self, client: FlaskClient, auth: dict[str, str]) -> None:
        client.post(
            "/v1/phones", json={"phone_number": "+2250700000002", "country": "CI"}, headers=auth
        )
        resp = client.delete(
            "/v1/phones", json={"phone_number": PRIMARY, "country": "CI"}, headers=auth
        )
        assert resp.status_code in (409, 422)
        assert resp.get_json()["code"] == "CANNOT_REMOVE_PRIMARY_PHONE_NUMBER"

    def test_add_number_of_another_account_is_409(
        self, client: FlaskClient, auth: dict[str, str]
    ) -> None:
        # deuxième compte possède déjà +...99
        client.post(
            "/v1/auth/register",
            json={"phone_number": "+2250700000099", "pin": "1397", "country": "CI"},
            headers={"Idempotency-Key": "other-account-key"},
        )
        resp = client.post(
            "/v1/phones", json={"phone_number": "+2250700000099", "country": "CI"}, headers=auth
        )
        assert resp.status_code == 409
        assert resp.get_json()["code"] == "PHONE_NUMBER_ALREADY_LINKED"

    def test_routes_documented_and_secured(self, client: FlaskClient) -> None:
        paths = client.get("/openapi.json").get_json()["paths"]
        for route in ("/v1/phones", "/v1/phones/verify", "/v1/phones/primary"):
            assert route in paths
        assert "security" in paths["/v1/phones"]["get"]
