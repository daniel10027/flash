"""Tests du blueprint ``savings`` (BE-054) : plan, versement, retrait, clôture."""

from __future__ import annotations

from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient

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


def _login(client: FlaskClient, phone: str, key: str) -> dict[str, str]:
    client.post(
        "/v1/auth/register",
        json={"phone_number": phone, "pin": "1397", "country": "CI"},
        headers={"Idempotency-Key": key},
    )
    tokens = client.post(
        "/v1/auth/verify-otp",
        json={"phone_number": phone, "country": "CI", "code": "000000", "device_id": "d1"},
    ).get_json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _fund(uow: InMemoryUnitOfWork, phone: str, amount: int) -> None:
    user = uow.users.get_by_msisdn(Msisdn(phone))
    assert user is not None
    wallet = uow.wallets.list_for_user(user.id)[0]
    wallet.credit(Money(amount, XOF), FixedClock().now())
    wallet.pull_events()


class TestSavingsEndpoints:
    def test_open_contribute_withdraw_close_flow(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, uow, _deps = app_and_uow
        client = app.test_client()
        auth = _login(client, PHONE, "sav-setup-key")
        _fund(uow, PHONE, 100_000)

        opened = client.post(
            "/v1/savings/plans",
            headers=auth,
            json={"name": "Voyage", "annual_rate_bps": 350, "target_minor": 500_000},
        )
        assert opened.status_code == 201
        plan_id = opened.get_json()["plan_id"]

        dep = client.post(
            f"/v1/savings/plans/{plan_id}/deposit",
            headers={**auth, "Idempotency-Key": "sav-dep-0001"},
            json={"amount_minor": 40_000},
        )
        assert dep.status_code == 201
        body = dep.get_json()
        assert body["direction"] == "in"
        assert body["wallet_available_after_minor"] == 60_000
        assert body["saved_after_minor"] == 40_000

        wallet = client.get("/v1/wallets", headers=auth).get_json()["wallets"][0]
        assert wallet["available_minor"] == 60_000
        assert wallet["saved_minor"] == 40_000
        assert wallet["balance_minor"] == 100_000

        wd = client.post(
            f"/v1/savings/plans/{plan_id}/withdraw",
            headers={**auth, "Idempotency-Key": "sav-wd-0001"},
            json={"amount_minor": 15_000},
        )
        assert wd.status_code == 201
        assert wd.get_json()["wallet_available_after_minor"] == 75_000

        closed = client.post(f"/v1/savings/plans/{plan_id}/close", headers=auth)
        assert closed.status_code == 200
        assert closed.get_json()["returned_minor"] == 25_000

        plans = client.get("/v1/savings/plans", headers=auth).get_json()["plans"]
        assert plans[0]["status"] == "CLOSED"
        final = client.get("/v1/wallets", headers=auth).get_json()["wallets"][0]
        assert final["available_minor"] == 100_000 and final["saved_minor"] == 0

    def test_deposit_requires_idempotency_key(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, uow, _deps = app_and_uow
        client = app.test_client()
        auth = _login(client, PHONE, "sav-setup-idem")
        _fund(uow, PHONE, 10_000)
        plan_id = client.post(
            "/v1/savings/plans", headers=auth, json={"name": "X"}
        ).get_json()["plan_id"]
        resp = client.post(
            f"/v1/savings/plans/{plan_id}/deposit", headers=auth, json={"amount_minor": 1_000}
        )
        assert resp.status_code == 400

    def test_bad_frequency_is_422(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, _uow, _deps = app_and_uow
        client = app.test_client()
        auth = _login(client, PHONE, "sav-setup-freq")
        resp = client.post(
            "/v1/savings/plans", headers=auth, json={"name": "X", "frequency": "DAILY"}
        )
        assert resp.status_code == 422

    def test_scheduled_job_endpoints_need_admin_key(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, _uow, _deps = app_and_uow
        client = app.test_client()
        assert client.post("/v1/admin/jobs/savings/contributions").status_code == 403
        ok = client.post(
            "/v1/admin/jobs/savings/interest", headers={"X-Admin-Key": "test-admin-key"}
        )
        assert ok.status_code == 200 and ok.get_json()["checked"] == 0

    def test_requires_auth(self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]) -> None:
        app, _uow, _deps = app_and_uow
        assert app.test_client().get("/v1/savings/plans").status_code == 401
