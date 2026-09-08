"""Tests de la fabrique Flask : santé, gestion d'erreurs, contexte de requête (BE-021)."""

from __future__ import annotations

import pytest
from flask import Flask
from flask.testing import FlaskClient

from flash.domain.shared.errors import InsufficientFunds, KycRequired
from flash.infrastructure.config import Settings
from flash.interface.app import create_app


@pytest.fixture
def app() -> Flask:
    application = create_app(
        Settings(
            FLASH_ENV="test", FLASH_SECRET_KEY="flash-test-secret-please-ignore-0123456789abcd"
        )
    )

    @application.get("/_boom/domain")
    def _boom_domain() -> str:
        raise InsufficientFunds("plus de fonds", shortfall=500)

    @application.get("/_boom/kyc")
    def _boom_kyc() -> str:
        raise KycRequired(1)

    @application.get("/_boom/unexpected")
    def _boom_unexpected() -> str:
        raise RuntimeError("inattendu")

    return application


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()


class TestHealth:
    def test_health_is_ok(self, client: FlaskClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.get_json() == {"status": "ok"}

    def test_ready_reports_database_state(self, client: FlaskClient) -> None:
        resp = client.get("/health/ready")
        # Pas de base branchée dans ce test unitaire : dégradé mais pas d'exception.
        assert resp.status_code in (200, 503)
        body = resp.get_json()
        assert "database" in body["checks"]


class TestRequestContext:
    def test_request_id_echoed_and_generated(self, client: FlaskClient) -> None:
        resp = client.get("/health")
        assert resp.headers.get("X-Request-ID")

        resp2 = client.get("/health", headers={"X-Request-ID": "abc-123"})
        assert resp2.headers["X-Request-ID"] == "abc-123"

    def test_cors_headers_only_for_allowed_origin(self, client: FlaskClient) -> None:
        allowed = client.get("/health", headers={"Origin": "http://localhost:5173"})
        assert allowed.headers.get("Access-Control-Allow-Origin") == "http://localhost:5173"

        blocked = client.get("/health", headers={"Origin": "https://evil.example"})
        assert "Access-Control-Allow-Origin" not in blocked.headers


class TestErrorHandling:
    def test_domain_error_maps_to_422_with_stable_payload(self, client: FlaskClient) -> None:
        resp = client.get("/_boom/domain")
        assert resp.status_code == 422
        assert resp.get_json() == {
            "code": "INSUFFICIENT_FUNDS",
            "message": "plus de fonds",
            "details": {"shortfall": 500},
        }

    def test_kyc_required_carries_min_tier(self, client: FlaskClient) -> None:
        resp = client.get("/_boom/kyc")
        assert resp.status_code == 422
        assert resp.get_json()["code"] == "KYC_REQUIRED"
        assert resp.get_json()["details"] == {"min_tier": 1}

    def test_unknown_route_is_404_json(self, client: FlaskClient) -> None:
        resp = client.get("/nope")
        assert resp.status_code == 404
        assert resp.get_json()["code"] == "NOT_FOUND"

    def test_unexpected_error_is_500_json_without_leak(self, client: FlaskClient) -> None:
        resp = client.get("/_boom/unexpected")
        assert resp.status_code == 500
        body = resp.get_json()
        assert body["code"] == "INTERNAL_ERROR"
        assert "inattendu" not in body["message"]
