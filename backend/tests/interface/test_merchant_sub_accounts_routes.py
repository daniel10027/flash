"""Routes : caisses / employés (libre-service marchand) + frais par canal (back-office).

Reste de BE-068.
"""

from __future__ import annotations

from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient

from flash.application.merchants.operations import EnrollMerchant, EnrollMerchantCommand
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
ADMIN = {"X-Admin-Key": "test-admin-key"}
MERCHANT_PHONE = "+2250700000009"
PAYER_PHONE = "+2250700000001"


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


def _enroll(uow: InMemoryUnitOfWork, deps: Any, *, fee_bps: int = 80) -> str:
    merchant_user = uow.users.get_by_msisdn(Msisdn(MERCHANT_PHONE))
    assert merchant_user is not None
    view = EnrollMerchant(services=deps.services).execute(
        EnrollMerchantCommand(
            user_id=str(merchant_user.id), display_name="Chez Awa", fee_bps=fee_bps
        )
    )
    return view.merchant_id


def _fund_payer(uow: InMemoryUnitOfWork) -> None:
    wallet = uow.wallets.list_for_user(
        uow.users.get_by_msisdn(Msisdn(PAYER_PHONE)).id  # type: ignore[union-attr]
    )[0]
    wallet.credit(Money(100_000, XOF), FixedClock().now())
    wallet.pull_events()


class TestSubAccountRoutes:
    def test_crud_and_attribution(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, uow, deps = app_and_uow
        client = app.test_client()
        merchant_auth = _login(client, MERCHANT_PHONE, "sa-m-setup")
        payer_auth = _login(client, PAYER_PHONE, "sa-p-setup")
        _fund_payer(uow)
        merchant_id = _enroll(uow, deps)

        created = client.post(
            "/v1/merchant/sub-accounts",
            headers=merchant_auth,
            json={"kind": "TILL", "label": "Caisse 1", "external_ref": "T-01"},
        )
        assert created.status_code == 201
        till_id = created.get_json()["id"]

        listed = client.get("/v1/merchant/sub-accounts", headers=merchant_auth).get_json()
        assert [s["label"] for s in listed["sub_accounts"]] == ["Caisse 1"]

        pay = client.post(
            "/v1/merchant-payments",
            headers={**payer_auth, "Idempotency-Key": "sa-pay-key-0001"},
            json={
                "merchant_id": merchant_id,
                "amount_minor": 10_000,
                "sub_account_id": till_id,
            },
        )
        assert pay.status_code == 201

        filtered = client.get(
            f"/v1/merchant/payments?sub_account_id={till_id}", headers=merchant_auth
        ).get_json()
        assert [p["sub_account_id"] for p in filtered["payments"]] == [till_id]

        patched = client.patch(
            f"/v1/merchant/sub-accounts/{till_id}",
            headers=merchant_auth,
            json={"active": False},
        )
        assert patched.status_code == 200 and patched.get_json()["active"] is False

        blocked = client.post(
            "/v1/merchant-payments",
            headers={**payer_auth, "Idempotency-Key": "sa-pay-key-0002"},
            json={
                "merchant_id": merchant_id,
                "amount_minor": 1_000,
                "sub_account_id": till_id,
            },
        )
        assert blocked.status_code == 422

    def test_bad_kind_is_422(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, uow, deps = app_and_uow
        client = app.test_client()
        merchant_auth = _login(client, MERCHANT_PHONE, "sa-m-setup2")
        _enroll(uow, deps)
        resp = client.post(
            "/v1/merchant/sub-accounts",
            headers=merchant_auth,
            json={"kind": "DRONE", "label": "x"},
        )
        assert resp.status_code == 422


class TestChannelFeeRoutes:
    def test_set_get_clear_and_effect_on_payment(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, uow, deps = app_and_uow
        client = app.test_client()
        _login(client, MERCHANT_PHONE, "cf-m-setup")
        payer_auth = _login(client, PAYER_PHONE, "cf-p-setup")
        _fund_payer(uow)
        merchant_id = _enroll(uow, deps, fee_bps=80)

        assert (
            client.put(
                f"/v1/admin/merchants/{merchant_id}/channel-fees/QR",
                headers=ADMIN,
                json={"fee_bps": 150},
            ).status_code
            == 200
        )
        fees = client.get(
            f"/v1/admin/merchants/{merchant_id}/fees", headers=ADMIN
        ).get_json()
        assert fees["default_fee_bps"] == 80 and fees["channel_fees"] == {"QR": 150}

        # un paiement QR statique applique désormais 1,5 %
        pay = client.post(
            "/v1/merchant-payments",
            headers={**payer_auth, "Idempotency-Key": "cf-pay-key-0001"},
            json={"merchant_id": merchant_id, "amount_minor": 10_000},
        )
        assert pay.get_json()["fee_minor"] == 150

        assert (
            client.delete(
                f"/v1/admin/merchants/{merchant_id}/channel-fees/QR", headers=ADMIN
            ).status_code
            == 200
        )
        pay2 = client.post(
            "/v1/merchant-payments",
            headers={**payer_auth, "Idempotency-Key": "cf-pay-key-0002"},
            json={"merchant_id": merchant_id, "amount_minor": 10_000},
        )
        assert pay2.get_json()["fee_minor"] == 80

    def test_requires_admin_role(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, uow, deps = app_and_uow
        client = app.test_client()
        _login(client, MERCHANT_PHONE, "cf-role-setup")
        merchant_id = _enroll(uow, deps)
        assert (
            client.put(
                f"/v1/admin/merchants/{merchant_id}/channel-fees/API",
                json={"fee_bps": 100},
            ).status_code
            == 403
        )

    def test_bad_channel_is_422(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, uow, deps = app_and_uow
        client = app.test_client()
        _login(client, MERCHANT_PHONE, "cf-badchan-setup")
        merchant_id = _enroll(uow, deps)
        assert (
            client.put(
                f"/v1/admin/merchants/{merchant_id}/channel-fees/SMS",
                headers=ADMIN,
                json={"fee_bps": 100},
            ).status_code
            == 422
        )


def test_routes_in_openapi(app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]) -> None:
    app, _uow, _deps = app_and_uow
    paths = app.test_client().get("/openapi.json").get_json()["paths"]
    assert "/v1/merchant/sub-accounts" in paths
    assert "/v1/merchant/sub-accounts/{sub_account_id}" in paths
    assert "/v1/admin/merchants/{merchant_id}/channel-fees/{channel}" in paths
