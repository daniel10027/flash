"""Tests du blueprint auth : register, verify-otp, resend-otp, login, refresh, logout
(BE-025 → BE-027)."""

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
_BODY = {"phone_number": "+2250700000001", "pin": "1397", "country": "CI"}


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


def _register(client: FlaskClient, key: str = "regkey-0001") -> dict[str, Any]:
    resp = client.post("/v1/auth/register", json=_BODY, headers={"Idempotency-Key": key})
    return dict(resp.get_json())


class TestRegister:
    def test_happy_path_returns_201(self, client: FlaskClient, otp: RecordingOtpService) -> None:
        resp = client.post("/v1/auth/register", json=_BODY, headers={"Idempotency-Key": "regkey-1"})
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["currency"] == "XOF"
        assert body["activation_required"] is True
        assert "***" in body["phone_number_masked"]
        assert len(otp.issued) == 1

    def test_missing_idempotency_key_is_400(self, client: FlaskClient) -> None:
        assert client.post("/v1/auth/register", json=_BODY).status_code == 400

    def test_replay_same_key(self, client: FlaskClient) -> None:
        first = _register(client, "same-key-0001")
        second = _register(client, "same-key-0001")
        assert first["user_id"] == second["user_id"]

    def test_unknown_field_is_422(self, client: FlaskClient) -> None:
        resp = client.post(
            "/v1/auth/register", json={**_BODY, "x": 1}, headers={"Idempotency-Key": "k12345678"}
        )
        assert resp.status_code == 422
        assert resp.get_json()["code"] == "VALIDATION_ERROR"

    def test_trivial_pin_is_422(self, client: FlaskClient) -> None:
        resp = client.post(
            "/v1/auth/register",
            json={**_BODY, "pin": "1234"},
            headers={"Idempotency-Key": "k12345678"},
        )
        assert resp.status_code == 422
        assert resp.get_json()["code"] == "INVALID_INPUT"

    def test_duplicate_number_is_409(self, client: FlaskClient) -> None:
        _register(client, "dupkey-1")
        resp = client.post("/v1/auth/register", json=_BODY, headers={"Idempotency-Key": "dupkey-2"})
        assert resp.status_code == 409
        assert resp.get_json()["code"] == "PHONE_NUMBER_ALREADY_LINKED"


class TestActivationAndLogin:
    def test_verify_otp_activates_and_returns_tokens(self, client: FlaskClient) -> None:
        _register(client)
        resp = client.post(
            "/v1/auth/verify-otp",
            json={
                **{k: _BODY[k] for k in ("phone_number", "country")},
                "code": "000000",
                "device_id": "dev-1",
            },
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["access_token"] and body["refresh_token"]
        assert body["access_expires_in"] == 900

    def test_verify_wrong_code_is_422(self, client: FlaskClient) -> None:
        _register(client)
        resp = client.post(
            "/v1/auth/verify-otp",
            json={
                "phone_number": _BODY["phone_number"],
                "country": "CI",
                "code": "999999",
                "device_id": "d",
            },
        )
        assert resp.status_code == 422
        assert resp.get_json()["code"] == "OTP_INVALID"

    def test_verify_twice_is_rejected(self, client: FlaskClient) -> None:
        _register(client)
        payload = {
            "phone_number": _BODY["phone_number"],
            "country": "CI",
            "code": "000000",
            "device_id": "d",
        }
        assert client.post("/v1/auth/verify-otp", json=payload).status_code == 200
        assert client.post("/v1/auth/verify-otp", json=payload).status_code == 422

    def test_resend_otp_is_generic_and_issues_again(
        self, client: FlaskClient, otp: RecordingOtpService
    ) -> None:
        _register(client)
        resp = client.post(
            "/v1/auth/resend-otp",
            json={"phone_number": _BODY["phone_number"], "country": "CI"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["resent"] is True
        assert len(otp.issued) == 2  # register + resend

    def test_resend_for_unknown_number_still_200(self, client: FlaskClient) -> None:
        resp = client.post(
            "/v1/auth/resend-otp", json={"phone_number": "+2250799999999", "country": "CI"}
        )
        assert resp.status_code == 200

    def test_login_before_activation_is_422(self, client: FlaskClient) -> None:
        _register(client)
        resp = client.post("/v1/auth/login", json={**_BODY, "device_id": "d"})
        assert resp.status_code == 422
        assert resp.get_json()["code"] == "INVALID_ACCOUNT_STATE"

    def test_full_flow_register_verify_login_refresh_logout(self, client: FlaskClient) -> None:
        _register(client)
        client.post(
            "/v1/auth/verify-otp",
            json={
                "phone_number": _BODY["phone_number"],
                "country": "CI",
                "code": "000000",
                "device_id": "dev-1",
            },
        )
        login = client.post("/v1/auth/login", json={**_BODY, "device_id": "dev-1"})
        assert login.status_code == 200
        tokens = login.get_json()

        refreshed = client.post("/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert refreshed.status_code == 200
        new_tokens = refreshed.get_json()
        assert new_tokens["refresh_token"] != tokens["refresh_token"]

        # ancien refresh rejoué -> 401
        replay = client.post("/v1/auth/refresh", json={"refresh_token": tokens["refresh_token"]})
        assert replay.status_code == 401
        assert replay.get_json()["code"] == "INVALID_TOKEN"

        out = client.post(
            "/v1/auth/logout",
            headers={"Authorization": f"Bearer {new_tokens['access_token']}"},
        )
        assert out.status_code == 204
        # l'access token révoqué ne passe plus
        again = client.post(
            "/v1/auth/logout",
            headers={"Authorization": f"Bearer {new_tokens['access_token']}"},
        )
        assert again.status_code == 401

    def test_login_wrong_pin_is_401_generic(self, client: FlaskClient) -> None:
        _register(client)
        client.post(
            "/v1/auth/verify-otp",
            json={
                "phone_number": _BODY["phone_number"],
                "country": "CI",
                "code": "000000",
                "device_id": "d",
            },
        )
        resp = client.post("/v1/auth/login", json={**_BODY, "pin": "9753", "device_id": "d"})
        assert resp.status_code == 401
        assert resp.get_json()["code"] == "INVALID_CREDENTIALS"

    def test_login_unknown_number_is_401_generic(self, client: FlaskClient) -> None:
        resp = client.post(
            "/v1/auth/login",
            json={
                "phone_number": "+2250788888888",
                "country": "CI",
                "pin": "1397",
                "device_id": "d",
            },
        )
        assert resp.status_code == 401
        assert resp.get_json()["code"] == "INVALID_CREDENTIALS"


class TestOpenApi:
    def test_auth_routes_documented(self, client: FlaskClient) -> None:
        paths = client.get("/openapi.json").get_json()["paths"]
        for route in (
            "/v1/auth/register",
            "/v1/auth/verify-otp",
            "/v1/auth/resend-otp",
            "/v1/auth/login",
            "/v1/auth/refresh",
            "/v1/auth/logout",
        ):
            assert route in paths
        assert "security" in paths["/v1/auth/logout"]["post"]
        assert "security" not in paths["/v1/auth/login"]["post"]
