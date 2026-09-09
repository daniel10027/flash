"""Tests du blueprint ``reference`` (BE-061) — public, sans authentification."""

from __future__ import annotations

import pytest
from flask import Flask

from flash.infrastructure.config import Settings
from flash.interface.app import create_app
from tests.support.deps import build_test_deps
from tests.support.otp import RecordingOtpService
from tests.support.repositories import InMemoryUnitOfWork
from tests.support.security import build_test_security

SECRET = "flash-test-secret-please-ignore-0123456789abcd"


@pytest.fixture
def app() -> Flask:
    bundle = build_test_security()
    deps = build_test_deps(uow=InMemoryUnitOfWork(), otp=RecordingOtpService(), bundle=bundle)
    return create_app(
        Settings(FLASH_ENV="test", FLASH_SECRET_KEY=SECRET),
        security_bundle=bundle,
        deps=deps,
    )


def test_list_countries_is_public(app: Flask) -> None:
    resp = app.test_client().get("/v1/reference/countries")
    assert resp.status_code == 200
    countries = resp.get_json()["countries"]
    codes = {c["code"] for c in countries}
    assert {"CI", "SN", "CM"} <= codes
    ci = next(c for c in countries if c["code"] == "CI")
    assert ci["currency"] == "XOF"
    assert any(o["code"] == "ORANGE_CI" for o in ci["operators"])


def test_get_country_detail(app: Flask) -> None:
    resp = app.test_client().get("/v1/reference/countries/sn")
    assert resp.status_code == 200
    assert resp.get_json()["dialing_code"] == "221"


def test_get_unknown_country_is_422(app: Flask) -> None:
    resp = app.test_client().get("/v1/reference/countries/us")
    assert resp.status_code == 422
    assert resp.get_json()["code"] == "UNSUPPORTED_COUNTRY"


def test_openapi_marks_reference_public(app: Flask) -> None:
    spec = app.test_client().get("/openapi.json").get_json()
    op = spec["paths"]["/v1/reference/countries"]["get"]
    assert "security" not in op
