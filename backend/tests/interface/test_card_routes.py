"""Tests des blueprints carte (BE-060) : titulaire + webhook réseau signé."""

from __future__ import annotations

import hashlib
import hmac
import json
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
WEBHOOK_SECRET = "test-card-webhook-secret"
PHONE = "+2250700000001"


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


@pytest.fixture
def app_and_uow(uow: InMemoryUnitOfWork) -> tuple[Flask, InMemoryUnitOfWork, Any]:
    bundle = build_test_security()
    deps = build_test_deps(
        uow=uow, otp=RecordingOtpService(), bundle=bundle, card_webhook_secret=WEBHOOK_SECRET
    )
    app = create_app(
        Settings(FLASH_ENV="test", FLASH_SECRET_KEY=SECRET),
        security_bundle=bundle,
        deps=deps,
    )
    return app, uow, deps


def _login(client: FlaskClient, key: str) -> dict[str, str]:
    client.post(
        "/v1/auth/register",
        json={"phone_number": PHONE, "pin": "1397", "country": "CI"},
        headers={"Idempotency-Key": key},
    )
    tokens = client.post(
        "/v1/auth/verify-otp",
        json={"phone_number": PHONE, "country": "CI", "code": "000000", "device_id": "d1"},
    ).get_json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _fund(uow: InMemoryUnitOfWork, amount: int) -> None:
    user = uow.users.get_by_msisdn(Msisdn(PHONE))
    assert user is not None
    wallet = uow.wallets.list_for_user(user.id)[0]
    wallet.credit(Money(amount, XOF), FixedClock().now())
    wallet.pull_events()


def _signed(client: FlaskClient, path: str, payload: dict[str, Any]) -> Any:
    body = json.dumps(payload).encode()
    sig = hmac.new(WEBHOOK_SECRET.encode(), body, hashlib.sha256).hexdigest()
    return client.post(
        path, data=body, content_type="application/json", headers={"X-Card-Signature": sig}
    )


class TestCardHolderEndpoints:
    def test_issue_list_freeze_limits_reveal(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, _uow, _deps = app_and_uow
        client = app.test_client()
        auth = _login(client, "card-setup-key")

        issued = client.post("/v1/cards", headers=auth, json={"network": "MASTERCARD"})
        assert issued.status_code == 201
        card = issued.get_json()
        assert card["network"] == "MASTERCARD" and card["status"] == "ACTIVE"
        card_id = card["card_id"]

        assert client.get("/v1/cards", headers=auth).get_json()["cards"][0]["card_id"] == card_id
        assert (
            client.post(f"/v1/cards/{card_id}/freeze", headers=auth).get_json()["status"]
            == "FROZEN"
        )
        assert (
            client.post(f"/v1/cards/{card_id}/unfreeze", headers=auth).get_json()["status"]
            == "ACTIVE"
        )

        limits = client.patch(
            f"/v1/cards/{card_id}/limits",
            headers=auth,
            json={"daily_limit_minor": 100_000, "monthly_limit_minor": 1_000_000},
        )
        assert limits.get_json()["daily_limit_minor"] == 100_000

        revealed = client.post(f"/v1/cards/{card_id}/reveal", headers=auth)
        assert revealed.status_code == 200
        assert revealed.headers["Cache-Control"] == "no-store"
        assert revealed.get_json()["pan"].endswith(card["last4"])

    def test_requires_auth(self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]) -> None:
        app, _uow, _deps = app_and_uow
        assert app.test_client().get("/v1/cards").status_code == 401


class TestCardWebhook:
    def test_authorize_capture_flow(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, uow, _deps = app_and_uow
        client = app.test_client()
        auth = _login(client, "card-wh-key")
        _fund(uow, 200_000)
        card = client.post("/v1/cards", headers=auth).get_json()

        authz = _signed(
            client,
            "/v1/cards/authorizations",
            {
                "authorization_id": "wh-auth-0001",
                "pan_token": _pan_token(uow, card["card_id"]),
                "amount_minor": 40_000,
                "channel": "ECOM",
                "merchant_name": "Café",
            },
        )
        assert authz.status_code == 200 and authz.get_json()["decision"] == "APPROVED"

        wallet = client.get("/v1/wallets", headers=auth).get_json()["wallets"][0]
        assert wallet["available_minor"] == 160_000 and wallet["reserved_minor"] == 40_000

        cap = _signed(client, "/v1/cards/authorizations/wh-auth-0001/capture", {})
        assert cap.status_code == 200 and cap.get_json()["status"] == "CAPTURED"
        wallet = client.get("/v1/wallets", headers=auth).get_json()["wallets"][0]
        assert wallet["available_minor"] == 160_000 and wallet["reserved_minor"] == 0
        assert wallet["balance_minor"] == 160_000

    def test_reverse_releases(self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]) -> None:
        app, uow, _deps = app_and_uow
        client = app.test_client()
        auth = _login(client, "card-wh-rev")
        _fund(uow, 200_000)
        card = client.post("/v1/cards", headers=auth).get_json()
        _signed(
            client,
            "/v1/cards/authorizations",
            {
                "authorization_id": "wh-auth-rev1",
                "pan_token": _pan_token(uow, card["card_id"]),
                "amount_minor": 40_000,
                "channel": "ECOM",
            },
        )
        rev = _signed(client, "/v1/cards/authorizations/wh-auth-rev1/reverse", {})
        assert rev.status_code == 200 and rev.get_json()["status"] == "REVERSED"
        wallet = client.get("/v1/wallets", headers=auth).get_json()["wallets"][0]
        assert wallet["available_minor"] == 200_000 and wallet["reserved_minor"] == 0

    def test_bad_signature_is_401(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, _uow, _deps = app_and_uow
        client = app.test_client()
        resp = client.post(
            "/v1/cards/authorizations",
            json={
                "authorization_id": "wh-auth-x",
                "pan_token": "tok_whatever",
                "amount_minor": 1_000,
                "channel": "ECOM",
            },
            headers={"X-Card-Signature": "deadbeef"},
        )
        assert resp.status_code == 401


def _pan_token(uow: InMemoryUnitOfWork, card_id: str) -> str:
    from flash.domain.shared.identifiers import EntityId

    card = uow.cards.get(EntityId(card_id))
    assert card is not None
    return card.pan_token
