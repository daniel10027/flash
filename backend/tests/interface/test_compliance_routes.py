"""Routes conformité / AML (BE-076) : file d'alertes, revue, alerte manuelle, export, job."""

from __future__ import annotations

from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient

from flash.domain.compliance.alert import AlertKind, ComplianceAlert
from flash.domain.shared.identifiers import EntityId, Msisdn
from flash.domain.shared.money import XOF, Money
from flash.infrastructure.config import Settings
from flash.interface.app import create_app
from tests.support.deps import build_test_deps
from tests.support.fakes import FixedClock
from tests.support.otp import RecordingOtpService
from tests.support.repositories import InMemoryUnitOfWork
from tests.support.security import build_test_security

SECRET = "flash-test-secret-please-ignore-0123456789abcd"
ADMIN_KEY = "test-admin-key"
COMPLIANCE_KEY = "test-compliance-key"
PHONE = "+2250700000001"


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


@pytest.fixture
def app_and_uow(uow: InMemoryUnitOfWork) -> tuple[Flask, InMemoryUnitOfWork, Any]:
    bundle = build_test_security()
    deps = build_test_deps(uow=uow, otp=RecordingOtpService(), bundle=bundle)
    app = create_app(
        Settings(FLASH_ENV="test", FLASH_SECRET_KEY=SECRET),
        security_bundle=bundle,
        deps=deps,
    )
    return app, uow, deps


def _register(client: FlaskClient, phone: str, key: str) -> str:
    client.post(
        "/v1/auth/register",
        json={"phone_number": phone, "pin": "1397", "country": "CI"},
        headers={"Idempotency-Key": key},
    )
    client.post(
        "/v1/auth/verify-otp",
        json={"phone_number": phone, "country": "CI", "code": "000000", "device_id": "d1"},
    )
    return ""


def _compliance() -> dict[str, str]:
    return {"X-Admin-Key": COMPLIANCE_KEY}


class TestComplianceRoutes:
    def test_requires_compliance_role(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, _uow, _deps = app_and_uow
        assert app.test_client().get("/v1/admin/compliance/alerts").status_code == 403

    def test_manual_alert_then_list_then_escalate_freezes(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, uow, _deps = app_and_uow
        client = app.test_client()
        _register(client, PHONE, "compliance-user-reg")
        user = uow.users.get_by_msisdn(Msisdn(PHONE))
        assert user is not None

        opened = client.post(
            "/v1/admin/compliance/alerts",
            headers=_compliance(),
            json={"user_id": str(user.id), "reason": "signalement externe"},
        )
        assert opened.status_code == 201
        alert_id = opened.get_json()["alert_id"]

        listed = client.get(
            "/v1/admin/compliance/alerts", headers=_compliance()
        ).get_json()
        assert [a["alert_id"] for a in listed["alerts"]] == [alert_id]

        escalated = client.post(
            f"/v1/admin/compliance/alerts/{alert_id}/review",
            headers=_compliance(),
            json={"decision": "escalate", "note": "STR déposée à la CENTIF"},
        )
        assert escalated.status_code == 200
        assert escalated.get_json()["status"] == "ESCALATED"
        assert uow.users.get(user.id).status.value == "FROZEN"  # type: ignore[union-attr]

        audit = client.get("/v1/admin/audit", headers={"X-Admin-Key": ADMIN_KEY}).get_json()
        assert "aml.alert.escalate" in [e["action"] for e in audit["entries"]]

    def test_scan_job_opens_alerts(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, uow, _deps = app_and_uow
        client = app.test_client()
        sender = _register_and_fund(client, uow)
        # 25 débits P2P -> vélocité (seuil test = 20)
        for i in range(25):
            client.post(
                "/v1/transfers",
                headers={
                    "Authorization": sender,
                    "Idempotency-Key": f"compliance-scan-transfer-{i}",
                },
                json={"recipient_phone_number": "+2250700000002", "amount_minor": 1_000},
            )
        run = client.post(
            "/v1/admin/jobs/compliance/scan", headers=_compliance()
        )
        assert run.status_code == 200
        assert run.get_json()["alerts_opened"] >= 1

    def test_scan_job_requires_role(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, _uow, _deps = app_and_uow
        assert (
            app.test_client().post("/v1/admin/jobs/compliance/scan").status_code == 403
        )

    def test_str_export_csv(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, uow, _deps = app_and_uow
        client = app.test_client()
        _register(client, PHONE, "compliance-export-reg")
        user = uow.users.get_by_msisdn(Msisdn(PHONE))
        assert user is not None
        alert = ComplianceAlert.open(
            alert_id=EntityId("00000000-0000-4000-8000-0000000000c1"),
            user_id=user.id,
            kind=AlertKind.CTR_THRESHOLD,
            score=90,
            detail={"amount_minor": 1_500_000},
            window_key="txn-1",
            now=FixedClock().now(),
        )
        alert.pull_events()
        uow.compliance_alerts.add(alert)

        resp = client.get(
            "/v1/admin/compliance/reports/str",
            query_string={
                "start": "2025-12-01T00:00:00+00:00",
                "end": "2026-12-01T00:00:00+00:00",
            },
            headers=_compliance(),
        )
        assert resp.status_code == 200
        assert resp.mimetype == "text/csv"
        assert "attachment" in resp.headers["Content-Disposition"]
        assert b"CTR_THRESHOLD" in resp.data


def _register_and_fund(client: FlaskClient, uow: InMemoryUnitOfWork) -> str:
    client.post(
        "/v1/auth/register",
        json={"phone_number": PHONE, "pin": "1397", "country": "CI"},
        headers={"Idempotency-Key": "compliance-fund-sender"},
    )
    tokens = client.post(
        "/v1/auth/verify-otp",
        json={"phone_number": PHONE, "country": "CI", "code": "000000", "device_id": "d1"},
    ).get_json()
    client.post(
        "/v1/auth/register",
        json={"phone_number": "+2250700000002", "pin": "1397", "country": "CI"},
        headers={"Idempotency-Key": "compliance-fund-recipient"},
    )
    client.post(
        "/v1/auth/verify-otp",
        json={
            "phone_number": "+2250700000002",
            "country": "CI",
            "code": "000000",
            "device_id": "d1",
        },
    )
    user = uow.users.get_by_msisdn(Msisdn(PHONE))
    assert user is not None
    wallet = uow.wallets.list_for_user(user.id)[0]
    wallet.credit(Money(1_000_000, XOF), FixedClock().now())
    wallet.pull_events()
    return f"Bearer {tokens['access_token']}"
