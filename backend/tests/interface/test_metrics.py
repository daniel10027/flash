"""BE-T4 : endpoint Prometheus /metrics + instrumentation des requêtes."""

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


@pytest.fixture
def client() -> FlaskClient:
    bundle = build_test_security()
    deps = build_test_deps(
        uow=InMemoryUnitOfWork(), otp=RecordingOtpService(), bundle=bundle
    )
    app: Flask = create_app(
        Settings(FLASH_ENV="test", FLASH_SECRET_KEY=SECRET),
        security_bundle=bundle,
        deps=deps,
    )
    return app.test_client()


def test_metrics_endpoint_exposes_prometheus_text(client: FlaskClient) -> None:
    resp = client.get("/metrics")
    assert resp.status_code == 200
    assert resp.mimetype == "text/plain"
    body = resp.get_data(as_text=True)
    assert "flash_http_requests_total" in body
    assert "flash_http_request_duration_seconds" in body
    assert "flash_http_requests_in_progress" in body


def test_requests_are_counted_by_endpoint_template_and_status(
    client: FlaskClient,
) -> None:
    client.get("/health")
    client.get("/v1/reference/countries")
    client.get("/v1/wallets")  # 401 : pas de jeton

    body = client.get("/metrics").get_data(as_text=True)
    assert 'flash_http_requests_total{endpoint="/health",method="GET",status="200"}' in body
    assert (
        'endpoint="/v1/reference/countries",method="GET",status="200"' in body
    )
    assert 'endpoint="/v1/wallets",method="GET",status="401"' in body


def test_metrics_scrape_is_not_self_counted(client: FlaskClient) -> None:
    client.get("/metrics")
    body = client.get("/metrics").get_data(as_text=True)
    assert 'endpoint="/metrics"' not in body


def test_each_app_has_its_own_registry(client: FlaskClient) -> None:
    # Un 2e app ne doit pas lever "Duplicated timeseries" ni cumuler les compteurs.
    bundle = build_test_security()
    deps = build_test_deps(
        uow=InMemoryUnitOfWork(), otp=RecordingOtpService(), bundle=bundle
    )
    other = create_app(
        Settings(FLASH_ENV="test", FLASH_SECRET_KEY=SECRET),
        security_bundle=bundle,
        deps=deps,
    ).test_client()
    other.get("/health")
    body = other.get("/metrics").get_data(as_text=True)
    assert 'flash_http_requests_total{endpoint="/health",method="GET",status="200"} 1.0' in body
