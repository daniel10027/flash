"""Tests du blueprint back-office référentiel + rôles + audit (BE-062)."""

from __future__ import annotations

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
ADMIN = {"X-Admin-Key": "test-admin-key"}
COMPLIANCE = {"X-Admin-Key": "test-compliance-key"}


@pytest.fixture
def client() -> FlaskClient:
    bundle = build_test_security()
    deps = build_test_deps(uow=InMemoryUnitOfWork(), otp=RecordingOtpService(), bundle=bundle)
    app: Flask = create_app(
        Settings(FLASH_ENV="test", FLASH_SECRET_KEY=SECRET), security_bundle=bundle, deps=deps
    )
    return app.test_client()


class TestRoleGating:
    def test_no_key_is_403(self, client: FlaskClient) -> None:
        assert client.get("/v1/admin/audit").status_code == 403

    def test_unknown_key_is_403(self, client: FlaskClient) -> None:
        assert (
            client.get("/v1/admin/audit", headers={"X-Admin-Key": "nope"}).status_code == 403
        )

    def test_compliance_can_manage_reference(self, client: FlaskClient) -> None:
        resp = client.put(
            "/v1/admin/reference/countries/ZA",
            headers=COMPLIANCE,
            json={"name": "Afrique du Sud", "currency": "XOF", "dialing_code": "27"},
        )
        assert resp.status_code == 200 and resp.get_json()["code"] == "ZA"

    def test_admin_can_manage_reference(self, client: FlaskClient) -> None:
        assert (
            client.put(
                "/v1/admin/reference/countries/ZW",
                headers=ADMIN,
                json={"name": "Zimbabwe", "currency": "XOF", "dialing_code": "263"},
            ).status_code
            == 200
        )

    def test_legacy_job_endpoint_still_admin_only(self, client: FlaskClient) -> None:
        assert client.post("/v1/admin/reconcile", headers=ADMIN).status_code == 200
        assert client.post("/v1/admin/reconcile", headers=COMPLIANCE).status_code == 403


class TestReferenceCrudFlow:
    def test_full_country_and_operator_lifecycle_is_audited(self, client: FlaskClient) -> None:
        client.put(
            "/v1/admin/reference/countries/KE",
            headers=COMPLIANCE,
            json={"name": "Kenya", "currency": "XOF", "dialing_code": "254"},
        )
        op = client.put(
            "/v1/admin/reference/countries/KE/operators/MPESA_KE",
            headers=COMPLIANCE,
            json={"name": "M-Pesa", "msisdn_prefixes": ["7"]},
        )
        assert op.status_code == 200 and op.get_json()["code"] == "MPESA_KE"

        # visible dans le référentiel public
        countries = client.get("/v1/reference/countries").get_json()["countries"]
        ke = next(c for c in countries if c["code"] == "KE")
        assert ke["operators"][0]["code"] == "MPESA_KE"

        assert (
            client.delete(
                "/v1/admin/reference/countries/KE/operators/MPESA_KE", headers=COMPLIANCE
            ).status_code
            == 204
        )
        assert client.delete("/v1/admin/reference/countries/KE", headers=ADMIN).status_code == 204

        audit = client.get("/v1/admin/audit?verify=1", headers=ADMIN).get_json()
        assert audit["intact"] is True
        actions = [e["action"] for e in audit["entries"]]
        assert actions == [
            "country.delete",
            "operator.delete",
            "operator.create",
            "country.create",
        ]
        assert audit["entries"][0]["actor"] == "key:admin"
        assert audit["entries"][1]["actor"] == "key:compliance"

    def test_upsert_validation_errors_are_422(self, client: FlaskClient) -> None:
        resp = client.put(
            "/v1/admin/reference/countries/CI",
            headers=ADMIN,
            json={"name": "X", "currency": "ZZZ", "dialing_code": "225"},
        )
        assert resp.status_code == 422

    def test_reload_endpoint_ok(self, client: FlaskClient) -> None:
        resp = client.post("/v1/admin/reference/reload", headers=ADMIN)
        assert resp.status_code == 200 and resp.get_json()["reloaded"] is True

    def test_routes_in_openapi(self, client: FlaskClient) -> None:
        paths = client.get("/openapi.json").get_json()["paths"]
        assert "/v1/admin/reference/countries/{code}" in paths
        assert "/v1/admin/audit" in paths
