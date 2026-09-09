"""Routes exports réglementaires & compta (BE-077) : balance, journal, export mensuel."""

from __future__ import annotations

from typing import Any

import pytest
from flask import Flask

from flash.domain.shared.identifiers import Msisdn
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
A_PHONE = "+2250700000001"
B_PHONE = "+2250700000002"


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


def _finance() -> dict[str, str]:
    # la clé "admin" a le rôle admin, autorisé sur les rapports finance
    return {"X-Admin-Key": ADMIN_KEY}


def _make_transfer(app: Flask, uow: InMemoryUnitOfWork) -> None:
    client = app.test_client()
    client.post(
        "/v1/auth/register",
        json={"phone_number": A_PHONE, "pin": "1397", "country": "CI"},
        headers={"Idempotency-Key": "reporting-sender-reg"},
    )
    tokens = client.post(
        "/v1/auth/verify-otp",
        json={"phone_number": A_PHONE, "country": "CI", "code": "000000", "device_id": "d1"},
    ).get_json()
    client.post(
        "/v1/auth/register",
        json={"phone_number": B_PHONE, "pin": "1397", "country": "CI"},
        headers={"Idempotency-Key": "reporting-recipient-reg"},
    )
    client.post(
        "/v1/auth/verify-otp",
        json={"phone_number": B_PHONE, "country": "CI", "code": "000000", "device_id": "d1"},
    )
    sender = uow.users.get_by_msisdn(Msisdn(A_PHONE))
    assert sender is not None
    wallet = uow.wallets.list_for_user(sender.id)[0]
    wallet.credit(Money(100_000, XOF), FixedClock().now())
    wallet.pull_events()
    client.post(
        "/v1/transfers",
        headers={
            "Authorization": f"Bearer {tokens['access_token']}",
            "Idempotency-Key": "reporting-transfer-1",
        },
        json={"recipient_phone_number": B_PHONE, "amount_minor": 10_000},
    )


class TestReportingRoutes:
    def test_requires_finance_or_admin(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, _uow, _deps = app_and_uow
        assert (
            app.test_client()
            .get("/v1/admin/reports/trial-balance?as_of=2026-01-01T00:00:00+00:00")
            .status_code
            == 403
        )
        assert (
            app.test_client()
            .get(
                "/v1/admin/reports/trial-balance?as_of=2026-01-01T00:00:00+00:00",
                headers={"X-Admin-Key": COMPLIANCE_KEY},
            )
            .status_code
            == 403
        )

    def test_trial_balance_is_balanced_after_a_transfer(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, uow, _deps = app_and_uow
        _make_transfer(app, uow)
        resp = app.test_client().get(
            "/v1/admin/reports/trial-balance",
            query_string={"as_of": "2026-12-31T23:59:59+00:00"},
            headers=_finance(),
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["balanced"] is True
        assert body["totals_by_currency"]["XOF"]["debit_minor"] == (
            body["totals_by_currency"]["XOF"]["credit_minor"]
        )

    def test_journal_lists_entries(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, uow, _deps = app_and_uow
        _make_transfer(app, uow)
        resp = app.test_client().get(
            "/v1/admin/reports/journal",
            query_string={
                "start": "2026-01-01T00:00:00+00:00",
                "end": "2027-01-01T00:00:00+00:00",
            },
            headers=_finance(),
        )
        assert resp.status_code == 200
        entries = resp.get_json()["entries"]
        assert len(entries) == 1 and entries[0]["kind"] == "TRANSFER"

    def test_monthly_export_csv(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, uow, _deps = app_and_uow
        _make_transfer(app, uow)
        clock_year = FixedClock().now().year
        clock_month = FixedClock().now().month
        resp = app.test_client().get(
            "/v1/admin/reports/monthly",
            query_string={"year": clock_year, "month": clock_month},
            headers=_finance(),
        )
        assert resp.status_code == 200
        assert resp.mimetype == "text/csv"
        assert "attachment" in resp.headers["Content-Disposition"]
        assert b"TRANSFER" in resp.data

    def test_monthly_export_bad_month_is_422(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, _uow, _deps = app_and_uow
        resp = app.test_client().get(
            "/v1/admin/reports/monthly",
            query_string={"year": 2026, "month": 0},
            headers=_finance(),
        )
        assert resp.status_code == 422

    def test_trial_balance_bad_date_is_422(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, _uow, _deps = app_and_uow
        resp = app.test_client().get(
            "/v1/admin/reports/trial-balance",
            query_string={"as_of": "hier"},
            headers=_finance(),
        )
        assert resp.status_code == 422
