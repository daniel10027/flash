"""Routes back-office grille tarifaire & plafonds (reste de BE-062)."""

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
        assert client.get("/v1/admin/reference/pricing").status_code == 403
        assert client.get("/v1/admin/reference/limits").status_code == 403

    def test_unknown_key_is_403(self, client: FlaskClient) -> None:
        assert (
            client.put(
                "/v1/admin/reference/pricing/CI/TRANSFER",
                headers={"X-Admin-Key": "nope"},
                json={"currency": "XOF", "percent_bps": 90},
            ).status_code
            == 403
        )


class TestPricingRoutes:
    def test_list_returns_seeded_defaults(self, client: FlaskClient) -> None:
        body = client.get("/v1/admin/reference/pricing", headers=ADMIN).get_json()
        keys = {(r["country"], r["operation"]) for r in body["rules"]}
        assert ("CI", "TRANSFER") in keys and ("SN", "TRANSFER") in keys

    def test_upsert_then_read_back_and_audit(self, client: FlaskClient) -> None:
        resp = client.put(
            "/v1/admin/reference/pricing/ci/transfer",
            headers=COMPLIANCE,
            json={"currency": "XOF", "percent_bps": 123, "rounding": "UP_TO_UNIT"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["percent_bps"] == 123

        rules = client.get("/v1/admin/reference/pricing", headers=ADMIN).get_json()["rules"]
        ci = next(r for r in rules if r["country"] == "CI" and r["operation"] == "TRANSFER")
        assert ci["percent_bps"] == 123

        audit = client.get("/v1/admin/audit", headers=ADMIN).get_json()["entries"]
        assert audit[0]["action"] == "pricing_rule.update"
        assert audit[0]["actor"] == "key:compliance"
        assert audit[0]["resource_id"] == "CI:TRANSFER"

    def test_delete(self, client: FlaskClient) -> None:
        assert (
            client.delete(
                "/v1/admin/reference/pricing/CI/MERCHANT_PAYMENT", headers=ADMIN
            ).status_code
            == 204
        )
        rules = client.get("/v1/admin/reference/pricing", headers=ADMIN).get_json()["rules"]
        assert not any(
            r["country"] == "CI" and r["operation"] == "MERCHANT_PAYMENT" for r in rules
        )

    def test_delete_unknown_is_422(self, client: FlaskClient) -> None:
        assert (
            client.delete(
                "/v1/admin/reference/pricing/ZZ/TRANSFER", headers=ADMIN
            ).status_code
            == 422
        )

    def test_bad_operation_is_422(self, client: FlaskClient) -> None:
        assert (
            client.put(
                "/v1/admin/reference/pricing/CI/FLYING",
                headers=ADMIN,
                json={"currency": "XOF"},
            ).status_code
            == 422
        )

    def test_bad_bps_is_422(self, client: FlaskClient) -> None:
        assert (
            client.put(
                "/v1/admin/reference/pricing/CI/TRANSFER",
                headers=ADMIN,
                json={"currency": "XOF", "percent_bps": 20_000},
            ).status_code
            == 422
        )


class TestLimitRoutes:
    def test_upsert_then_read_back(self, client: FlaskClient) -> None:
        resp = client.put(
            "/v1/admin/reference/limits/CI/1/TRANSFER",
            headers=ADMIN,
            json={"currency": "XOF", "per_tx_minor": 750_000, "balance_max_minor": 3_000_000},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["per_tx_minor"] == 750_000 and body["kyc_tier"] == 1

        rules = client.get("/v1/admin/reference/limits", headers=ADMIN).get_json()["rules"]
        row = next(
            r
            for r in rules
            if r["country"] == "CI" and r["kyc_tier"] == 1 and r["operation"] == "TRANSFER"
        )
        assert row["per_tx_minor"] == 750_000

    def test_upsert_without_any_cap_is_422(self, client: FlaskClient) -> None:
        assert (
            client.put(
                "/v1/admin/reference/limits/CI/1/TRANSFER",
                headers=ADMIN,
                json={"currency": "XOF"},
            ).status_code
            == 422
        )

    def test_delete(self, client: FlaskClient) -> None:
        client.put(
            "/v1/admin/reference/limits/CI/2/TRANSFER",
            headers=ADMIN,
            json={"currency": "XOF", "per_tx_minor": 1},
        )
        assert (
            client.delete(
                "/v1/admin/reference/limits/CI/2/TRANSFER", headers=ADMIN
            ).status_code
            == 204
        )


def test_routes_in_openapi(client: FlaskClient) -> None:
    paths = client.get("/openapi.json").get_json()["paths"]
    assert "/v1/admin/reference/pricing" in paths
    assert "/v1/admin/reference/pricing/{code}/{operation}" in paths
    assert "/v1/admin/reference/limits/{code}/{tier}/{operation}" in paths
