"""Tests du blueprint ``vault`` (BE-054) : poches, dépôt / reprise, verrouillage."""

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


class TestVaultEndpoints:
    def test_open_deposit_withdraw_flow(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, uow, _deps = app_and_uow
        client = app.test_client()
        auth = _login(client, PHONE, "v-setup-key")
        _fund(uow, PHONE, 100_000)

        opened = client.post(
            "/v1/vault/pockets",
            headers=auth,
            json={"name": "Vacances", "goal_minor": 200_000},
        )
        assert opened.status_code == 201
        pocket_id = opened.get_json()["pocket_id"]

        dep = client.post(
            f"/v1/vault/pockets/{pocket_id}/deposit",
            headers={**auth, "Idempotency-Key": "vault-dep-0001"},
            json={"amount_minor": 40_000},
        )
        assert dep.status_code == 201
        body = dep.get_json()
        assert body["direction"] == "in"
        assert body["wallet_available_after_minor"] == 60_000
        assert body["vaulted_after_minor"] == 40_000

        wallet = client.get("/v1/wallets", headers=auth).get_json()["wallets"][0]
        assert wallet["available_minor"] == 60_000
        assert wallet["vaulted_minor"] == 40_000
        assert wallet["balance_minor"] == 100_000

        wd = client.post(
            f"/v1/vault/pockets/{pocket_id}/withdraw",
            headers={**auth, "Idempotency-Key": "vault-wd-0001"},
            json={"amount_minor": 15_000},
        )
        assert wd.status_code == 201
        assert wd.get_json()["wallet_available_after_minor"] == 75_000

        vault = client.get("/v1/vault", headers=auth).get_json()
        assert vault["vaulted_minor"] == 25_000
        assert vault["pockets"][0]["progress_bps"] == 1_250

    def test_rename_and_close_pocket(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, _uow, _deps = app_and_uow
        client = app.test_client()
        auth = _login(client, PHONE, "v-setup-rc")

        pocket_id = client.post(
            "/v1/vault/pockets", headers=auth, json={"name": "Impôts"}
        ).get_json()["pocket_id"]

        renamed = client.patch(
            f"/v1/vault/pockets/{pocket_id}", headers=auth, json={"name": "Impôts 2027"}
        )
        assert renamed.status_code == 200 and renamed.get_json()["name"] == "Impôts 2027"

        closed = client.delete(f"/v1/vault/pockets/{pocket_id}", headers=auth)
        assert closed.status_code == 204
        assert client.get("/v1/vault", headers=auth).get_json()["pockets"] == []

    def test_withdraw_locked_pocket_is_rejected(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, uow, _deps = app_and_uow
        client = app.test_client()
        auth = _login(client, PHONE, "v-setup-lock")
        _fund(uow, PHONE, 100_000)

        pocket_id = client.post(
            "/v1/vault/pockets",
            headers=auth,
            json={"name": "Bloqué", "locked_until": "2027-01-01T00:00:00+00:00"},
        ).get_json()["pocket_id"]
        client.post(
            f"/v1/vault/pockets/{pocket_id}/deposit",
            headers={**auth, "Idempotency-Key": "vault-dep-lock"},
            json={"amount_minor": 10_000},
        )
        resp = client.post(
            f"/v1/vault/pockets/{pocket_id}/withdraw",
            headers={**auth, "Idempotency-Key": "vault-wd-lock"},
            json={"amount_minor": 1_000},
        )
        assert resp.status_code == 409
        assert resp.get_json()["code"] == "POCKET_LOCKED"

    def test_deposit_requires_idempotency_key(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, uow, _deps = app_and_uow
        client = app.test_client()
        auth = _login(client, PHONE, "v-setup-idem")
        _fund(uow, PHONE, 10_000)
        pocket_id = client.post(
            "/v1/vault/pockets", headers=auth, json={"name": "X"}
        ).get_json()["pocket_id"]
        resp = client.post(
            f"/v1/vault/pockets/{pocket_id}/deposit", headers=auth, json={"amount_minor": 1_000}
        )
        assert resp.status_code == 400

    def test_requires_auth(self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]) -> None:
        app, _uow, _deps = app_and_uow
        assert app.test_client().get("/v1/vault").status_code == 401
