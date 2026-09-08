"""Tests du blueprint auth : POST /v1/auth/register (BE-025)."""

from __future__ import annotations

import pytest
from flask import Flask
from flask.testing import FlaskClient

from flash.application.services import AppServices
from flash.domain.country.directory import StaticCountryDirectory
from flash.infrastructure.config import Settings
from flash.interface.app import create_app
from flash.interface.container import Deps
from tests.support.fakes import (
    FakePinHasher,
    FixedClock,
    InMemoryIdempotencyStore,
    RecordingEventPublisher,
    SeqIdGenerator,
)
from tests.support.otp import RecordingOtpService
from tests.support.repositories import InMemoryUnitOfWork
from tests.support.security import build_test_security

SECRET = "flash-test-secret-please-ignore-0123456789abcd"


@pytest.fixture
def otp() -> RecordingOtpService:
    return RecordingOtpService()


@pytest.fixture
def app(otp: RecordingOtpService) -> Flask:
    uow = InMemoryUnitOfWork()
    deps = Deps(
        services=AppServices(
            uow=lambda: uow,
            clock=FixedClock(),
            ids=SeqIdGenerator(),
            events=RecordingEventPublisher(),
            idempotency=InMemoryIdempotencyStore(),
        ),
        countries=StaticCountryDirectory(),
        pins=FakePinHasher(),
        otp=otp,
    )
    return create_app(
        Settings(FLASH_ENV="test", FLASH_SECRET_KEY=SECRET),
        security_bundle=build_test_security(),
        deps=deps,
    )


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()


_BODY = {"phone_number": "+2250700000001", "pin": "1397", "country": "CI"}


class TestRegisterEndpoint:
    def test_happy_path_returns_201_and_masked_number(
        self, client: FlaskClient, otp: RecordingOtpService
    ) -> None:
        resp = client.post("/v1/auth/register", json=_BODY, headers={"Idempotency-Key": "abcd1234"})
        assert resp.status_code == 201
        body = resp.get_json()
        assert body["currency"] == "XOF"
        assert body["activation_required"] is True
        assert (
            body["phone_number_masked"].startswith("+225") and "***" in body["phone_number_masked"]
        )
        assert len(otp.issued) == 1

    def test_missing_idempotency_key_is_400(self, client: FlaskClient) -> None:
        resp = client.post("/v1/auth/register", json=_BODY)
        assert resp.status_code == 400

    def test_replay_same_key_returns_same_result(self, client: FlaskClient) -> None:
        h = {"Idempotency-Key": "abcd1234"}
        first = client.post("/v1/auth/register", json=_BODY, headers=h).get_json()
        second = client.post("/v1/auth/register", json=_BODY, headers=h).get_json()
        assert first["user_id"] == second["user_id"]

    def test_unknown_field_is_422(self, client: FlaskClient) -> None:
        resp = client.post(
            "/v1/auth/register",
            json={**_BODY, "extra": "x"},
            headers={"Idempotency-Key": "abcd1234"},
        )
        assert resp.status_code == 422
        assert resp.get_json()["code"] == "VALIDATION_ERROR"

    def test_trivial_pin_is_422_invalid_input(self, client: FlaskClient) -> None:
        resp = client.post(
            "/v1/auth/register",
            json={**_BODY, "pin": "1234"},
            headers={"Idempotency-Key": "abcd1234"},
        )
        assert resp.status_code == 422
        assert resp.get_json()["code"] == "INVALID_INPUT"

    def test_duplicate_number_is_409(self, client: FlaskClient) -> None:
        client.post("/v1/auth/register", json=_BODY, headers={"Idempotency-Key": "dup-key-1"})
        resp = client.post(
            "/v1/auth/register", json=_BODY, headers={"Idempotency-Key": "dup-key-2"}
        )
        assert resp.status_code == 409
        assert resp.get_json()["code"] == "PHONE_NUMBER_ALREADY_LINKED"

    def test_route_is_in_openapi(self, client: FlaskClient) -> None:
        spec = client.get("/openapi.json").get_json()
        assert "/v1/auth/register" in spec["paths"]
        op = spec["paths"]["/v1/auth/register"]["post"]
        assert op["parameters"][0]["name"] == "Idempotency-Key"
        assert "security" not in op  # route publique
