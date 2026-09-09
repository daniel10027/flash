"""Tests du blueprint back-office : jobs d'expiration + réconciliation (BE-044/045)."""

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


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


@pytest.fixture
def client(uow: InMemoryUnitOfWork) -> FlaskClient:
    bundle = build_test_security()
    deps = build_test_deps(uow=uow, otp=RecordingOtpService(), bundle=bundle)
    app: Flask = create_app(
        Settings(FLASH_ENV="test", FLASH_SECRET_KEY=SECRET), security_bundle=bundle, deps=deps
    )
    return app.test_client()


class TestAdminOps:
    def test_reconcile_requires_admin_key(self, client: FlaskClient) -> None:
        assert client.post("/v1/admin/reconcile").status_code == 403
        assert client.post("/v1/admin/reconcile", headers={"X-Admin-Key": "no"}).status_code == 403

    def test_reconcile_ok_on_empty_system(self, client: FlaskClient) -> None:
        resp = client.post("/v1/admin/reconcile", headers=ADMIN)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is True and body["checked"] == 0 and body["discrepancies"] == []

    def test_expire_job_runs_and_reports_zero(self, client: FlaskClient) -> None:
        resp = client.post("/v1/admin/jobs/expire", headers=ADMIN)
        assert resp.status_code == 200
        assert resp.get_json()["total"] == 0

    def test_expire_job_requires_admin_key(self, client: FlaskClient) -> None:
        assert client.post("/v1/admin/jobs/expire").status_code == 403

    def test_routes_in_openapi(self, client: FlaskClient) -> None:
        paths = client.get("/openapi.json").get_json()["paths"]
        assert "/v1/admin/reconcile" in paths
        assert "/v1/admin/jobs/expire" in paths


class TestAdminKeyUnconfigured:
    def test_fail_closed_returns_403_not_500(self, uow: InMemoryUnitOfWork) -> None:
        # clé non configurée (chaîne vide / espaces) : la route doit refuser (403),
        # pas planter (régression : compare_digest sur str non-ASCII).
        bundle = build_test_security()
        deps = build_test_deps(
            uow=uow, otp=RecordingOtpService(), bundle=bundle, admin_api_key="   "
        )
        app = create_app(
            Settings(FLASH_ENV="test", FLASH_SECRET_KEY=SECRET),
            security_bundle=bundle,
            deps=deps,
        )
        client = app.test_client()
        assert client.post("/v1/admin/reconcile", headers=ADMIN).status_code == 403
        assert client.post("/v1/admin/reconcile").status_code == 403
