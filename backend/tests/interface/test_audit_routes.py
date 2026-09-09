"""Routes du registre d'audit consultable (BE-078) : filtres + contrôle d'intégrité."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest
from flask import Flask
from flask.testing import FlaskClient

from flash.infrastructure.config import Settings
from flash.interface.app import create_app
from tests.support.audit import InMemoryAuditLog
from tests.support.deps import build_test_deps
from tests.support.otp import RecordingOtpService
from tests.support.repositories import InMemoryUnitOfWork
from tests.support.security import build_test_security

SECRET = "flash-test-secret-please-ignore-0123456789abcd"
ADMIN = {"X-Admin-Key": "test-admin-key"}
COMPLIANCE = {"X-Admin-Key": "test-compliance-key"}
T0 = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


def _seed(log: InMemoryAuditLog) -> None:
    log.append(
        actor="key:admin", role="admin", action="country.create",
        resource_type="country", resource_id="CI", before=None, after={"n": 1}, now=T0,
    )
    log.append(
        actor="key:compliance", role="compliance", action="account.freeze",
        resource_type="account", resource_id="acc-1", before={"f": False},
        after={"f": True}, now=T0.replace(hour=13),
    )
    log.append(
        actor="key:admin", role="admin", action="account.freeze",
        resource_type="account", resource_id="acc-2", before={"f": False},
        after={"f": True}, now=T0.replace(day=5),
    )


@pytest.fixture
def client_and_audit() -> tuple[FlaskClient, InMemoryAuditLog]:
    bundle = build_test_security()
    deps = build_test_deps(uow=InMemoryUnitOfWork(), otp=RecordingOtpService(), bundle=bundle)
    assert isinstance(deps.audit, InMemoryAuditLog)
    _seed(deps.audit)
    app: Flask = create_app(
        Settings(FLASH_ENV="test", FLASH_SECRET_KEY=SECRET), security_bundle=bundle, deps=deps
    )
    return app.test_client(), deps.audit


class TestRoleGating:
    def test_no_key_is_403(self, client_and_audit: tuple[FlaskClient, InMemoryAuditLog]) -> None:
        client, _ = client_and_audit
        assert client.get("/v1/admin/audit").status_code == 403
        assert client.get("/v1/admin/audit/verify").status_code == 403

    def test_unknown_key_is_403(
        self, client_and_audit: tuple[FlaskClient, InMemoryAuditLog]
    ) -> None:
        client, _ = client_and_audit
        assert client.get("/v1/admin/audit", headers={"X-Admin-Key": "nope"}).status_code == 403

    def test_compliance_role_allowed(
        self, client_and_audit: tuple[FlaskClient, InMemoryAuditLog]
    ) -> None:
        client, _ = client_and_audit
        assert client.get("/v1/admin/audit", headers=COMPLIANCE).status_code == 200


class TestListAndFilters:
    def test_lists_newest_first(
        self, client_and_audit: tuple[FlaskClient, InMemoryAuditLog]
    ) -> None:
        client, _ = client_and_audit
        body = client.get("/v1/admin/audit", headers=ADMIN).get_json()
        assert [e["sequence"] for e in body["entries"]] == [3, 2, 1]
        assert "chain" not in body

    def test_filter_by_actor_action_resource(
        self, client_and_audit: tuple[FlaskClient, InMemoryAuditLog]
    ) -> None:
        client, _ = client_and_audit
        body = client.get(
            "/v1/admin/audit",
            query_string={"actor": "key:admin", "action": "account.freeze"},
            headers=ADMIN,
        ).get_json()
        assert [e["resource_id"] for e in body["entries"]] == ["acc-2"]

    def test_filter_by_period(
        self, client_and_audit: tuple[FlaskClient, InMemoryAuditLog]
    ) -> None:
        client, _ = client_and_audit
        body = client.get(
            "/v1/admin/audit",
            query_string={
                "start": "2026-03-01T00:00:00+00:00",
                "end": "2026-03-02T00:00:00+00:00",
            },
            headers=ADMIN,
        ).get_json()
        assert [e["sequence"] for e in body["entries"]] == [2, 1]

    def test_limit_and_cursor(
        self, client_and_audit: tuple[FlaskClient, InMemoryAuditLog]
    ) -> None:
        client, _ = client_and_audit
        body = client.get(
            "/v1/admin/audit",
            query_string={"limit": 1, "before_sequence": 3},
            headers=ADMIN,
        ).get_json()
        assert [e["sequence"] for e in body["entries"]] == [2]

    def test_verify_flag_joins_chain_report(
        self, client_and_audit: tuple[FlaskClient, InMemoryAuditLog]
    ) -> None:
        client, _ = client_and_audit
        body = client.get("/v1/admin/audit?verify=1", headers=ADMIN).get_json()
        assert body["intact"] is True
        assert body["chain"]["checked"] == 3

    def test_bad_date_is_422(
        self, client_and_audit: tuple[FlaskClient, InMemoryAuditLog]
    ) -> None:
        client, _ = client_and_audit
        assert (
            client.get(
                "/v1/admin/audit", query_string={"start": "hier"}, headers=ADMIN
            ).status_code
            == 422
        )


class TestVerifyRoute:
    def test_intact_chain_is_200(
        self, client_and_audit: tuple[FlaskClient, InMemoryAuditLog]
    ) -> None:
        client, _ = client_and_audit
        resp = client.get("/v1/admin/audit/verify", headers=ADMIN)
        assert resp.status_code == 200
        assert resp.get_json() == {
            "intact": True,
            "checked": 3,
            "broken_at": None,
            "reason": None,
        }

    def test_tampered_chain_is_409_and_locates_break(
        self, client_and_audit: tuple[FlaskClient, InMemoryAuditLog]
    ) -> None:
        client, audit = client_and_audit
        audit._entries[1] = replace(audit._entries[1], after={"f": "pirate"})
        resp = client.get("/v1/admin/audit/verify", headers=ADMIN)
        assert resp.status_code == 409
        body = resp.get_json()
        assert body["intact"] is False and body["broken_at"] == 2


def test_route_documented_in_openapi(
    client_and_audit: tuple[FlaskClient, InMemoryAuditLog],
) -> None:
    client, _ = client_and_audit
    paths = client.get("/openapi.json").get_json()["paths"]
    assert "/v1/admin/audit" in paths
    assert "/v1/admin/audit/verify" in paths
