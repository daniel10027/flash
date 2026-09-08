"""Tests des blueprints wallets + transfers, bout en bout HTTP (BE-030, BE-031)."""

from __future__ import annotations

from dataclasses import dataclass

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
def otp() -> RecordingOtpService:
    return RecordingOtpService()


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


@pytest.fixture
def app(otp: RecordingOtpService, uow: InMemoryUnitOfWork) -> Flask:
    bundle = build_test_security()
    deps = build_test_deps(uow=uow, otp=otp, bundle=bundle)
    return create_app(
        Settings(FLASH_ENV="test", FLASH_SECRET_KEY=SECRET), security_bundle=bundle, deps=deps
    )


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()


@dataclass(frozen=True, slots=True)
class Account:
    headers: dict[str, str]
    user_id: str
    wallet_id: str


def _onboard(client: FlaskClient, phone: str, key: str) -> Account:
    """Crée + active un compte et renvoie ses jetons et identifiants."""
    reg = client.post(
        "/v1/auth/register",
        json={"phone_number": phone, "pin": "1397", "country": "CI"},
        headers={"Idempotency-Key": key},
    ).get_json()
    tokens = client.post(
        "/v1/auth/verify-otp",
        json={"phone_number": phone, "country": "CI", "code": "000000", "device_id": "d"},
    ).get_json()
    return Account(
        headers={"Authorization": f"Bearer {tokens['access_token']}"},
        user_id=str(reg["user_id"]),
        wallet_id=str(reg["wallet_id"]),
    )


class TestWalletsEndpoints:
    def test_requires_auth(self, client: FlaskClient) -> None:
        assert client.get("/v1/wallets").status_code == 401

    def test_list_and_get_wallet(self, client: FlaskClient) -> None:
        a = _onboard(client, "+2250700000001", "w-key-1-longenough")
        listed = client.get("/v1/wallets", headers=a.headers).get_json()["wallets"]
        assert len(listed) == 1
        assert listed[0]["currency"] == "XOF"
        assert listed[0]["balance_minor"] == 0

        one = client.get(f"/v1/wallets/{a.wallet_id}", headers=a.headers)
        assert one.status_code == 200
        assert one.get_json()["id"] == a.wallet_id

    def test_get_other_users_wallet_is_404(self, client: FlaskClient) -> None:
        a = _onboard(client, "+2250700000001", "w-key-a-longenough")
        b = _onboard(client, "+2250700000002", "w-key-b-longenough")
        resp = client.get(f"/v1/wallets/{b.wallet_id}", headers=a.headers)
        assert resp.status_code == 404
        assert resp.get_json()["code"] == "WALLET_NOT_FOUND"


def _fund(uow: InMemoryUnitOfWork, wallet_id: str, amount_minor: int) -> None:
    """En l'absence d'endpoint de dépôt (BE-034), on crédite le portefeuille en direct."""
    from datetime import UTC, datetime

    from flash.domain.shared.identifiers import EntityId
    from flash.domain.shared.money import XOF, Money

    wallet = uow.wallets.get(EntityId(wallet_id))
    assert wallet is not None
    wallet.credit(Money(amount_minor, XOF), datetime(2026, 1, 1, tzinfo=UTC))
    wallet.pull_events()
    uow.wallets.save(wallet)


class TestTransferEndpoint:
    def test_transfer_requires_idempotency_key(self, client: FlaskClient) -> None:
        a = _onboard(client, "+2250700000001", "t-key-a-longenough")
        resp = client.post(
            "/v1/transfers",
            json={"recipient_phone_number": "+2250700000002", "amount_minor": 1000},
            headers=a.headers,
        )
        assert resp.status_code == 400

    def test_transfer_insufficient_funds_is_422(self, client: FlaskClient) -> None:
        a = _onboard(client, "+2250700000001", "t-key-a2-longenough")
        _onboard(client, "+2250700000002", "t-key-b2-longenough")
        resp = client.post(
            "/v1/transfers",
            json={"recipient_phone_number": "+2250700000002", "amount_minor": 1000},
            headers={**a.headers, "Idempotency-Key": "trx-http-1"},
        )
        assert resp.status_code == 422
        assert resp.get_json()["code"] == "INSUFFICIENT_FUNDS"

    def test_transfer_unknown_recipient_is_404(self, client: FlaskClient) -> None:
        a = _onboard(client, "+2250700000001", "t-key-a3-longenough")
        resp = client.post(
            "/v1/transfers",
            json={"recipient_phone_number": "+2250700009999", "amount_minor": 1000},
            headers={**a.headers, "Idempotency-Key": "trx-http-2"},
        )
        assert resp.status_code == 404
        assert resp.get_json()["code"] == "RECIPIENT_NOT_FOUND"

    def test_transfer_negative_amount_is_422(self, client: FlaskClient) -> None:
        a = _onboard(client, "+2250700000001", "t-key-a4-longenough")
        resp = client.post(
            "/v1/transfers",
            json={"recipient_phone_number": "+2250700000002", "amount_minor": -5},
            headers={**a.headers, "Idempotency-Key": "trx-http-3"},
        )
        assert resp.status_code == 422

    def test_successful_transfer_updates_balances_and_returns_receipt(
        self, client: FlaskClient, uow: InMemoryUnitOfWork
    ) -> None:
        sender = _onboard(client, "+2250700000001", "t-key-s-longenough")
        recipient = _onboard(client, "+2250700000002", "t-key-r-longenough")
        _fund(uow, sender.wallet_id, 100_000)

        resp = client.post(
            "/v1/transfers",
            json={
                "recipient_phone_number": "+2250700000002",
                "amount_minor": 25_000,
                "note": "loyer",
            },
            headers={**sender.headers, "Idempotency-Key": "trx-http-ok-1"},
        )
        assert resp.status_code == 201
        receipt = resp.get_json()
        assert receipt["amount_minor"] == 25_000
        assert receipt["fee_minor"] == 200  # 0,8 % de 25 000
        assert receipt["total_minor"] == 25_200
        assert receipt["sender_balance_after_minor"] == 74_800

        s = client.get("/v1/wallets", headers=sender.headers).get_json()["wallets"][0]
        r = client.get("/v1/wallets", headers=recipient.headers).get_json()["wallets"][0]
        assert s["balance_minor"] == 74_800
        assert r["balance_minor"] == 25_000

        # rejeu avec la même clé -> même reçu, pas de double débit
        replay = client.post(
            "/v1/transfers",
            json={"recipient_phone_number": "+2250700000002", "amount_minor": 25_000},
            headers={**sender.headers, "Idempotency-Key": "trx-http-ok-1"},
        )
        assert replay.status_code == 201
        assert replay.get_json()["transfer_id"] == receipt["transfer_id"]

    def test_routes_in_openapi(self, client: FlaskClient) -> None:
        paths = client.get("/openapi.json").get_json()["paths"]
        assert "/v1/wallets" in paths
        assert "/v1/wallets/{wallet_id}" in paths
        assert "/v1/transfers" in paths
        assert "/v1/statement" in paths
        transfer_op = paths["/v1/transfers"]["post"]
        assert transfer_op["parameters"][0]["name"] == "Idempotency-Key"
        assert "security" in transfer_op


class TestStatementEndpoint:
    def test_requires_auth(self, client: FlaskClient) -> None:
        assert client.get("/v1/statement").status_code == 401

    def test_shows_transfer_from_both_sides(
        self, client: FlaskClient, uow: InMemoryUnitOfWork
    ) -> None:
        sender = _onboard(client, "+2250700000001", "st-key-s-longenough")
        recipient = _onboard(client, "+2250700000002", "st-key-r-longenough")
        _fund(uow, sender.wallet_id, 100_000)
        client.post(
            "/v1/transfers",
            json={"recipient_phone_number": "+2250700000002", "amount_minor": 30_000, "note": "x"},
            headers={**sender.headers, "Idempotency-Key": "st-trx-0001"},
        )

        out = client.get("/v1/statement", headers=sender.headers).get_json()
        assert out["next_cursor"] is None
        assert len(out["lines"]) == 1
        assert out["lines"][0]["direction"] == "out"
        assert out["lines"][0]["amount_minor"] == 30_000
        assert out["lines"][0]["fee_minor"] == 240  # 0,8 %
        assert out["lines"][0]["note"] == "x"

        inc = client.get("/v1/statement", headers=recipient.headers).get_json()
        assert inc["lines"][0]["direction"] == "in"
        assert inc["lines"][0]["amount_minor"] == 30_000
        assert inc["lines"][0]["fee_minor"] == 0

    def test_pagination_via_query_params(
        self, client: FlaskClient, uow: InMemoryUnitOfWork
    ) -> None:
        sender = _onboard(client, "+2250700000001", "st-pg-s-longenough")
        _onboard(client, "+2250700000002", "st-pg-r-longenough")
        _fund(uow, sender.wallet_id, 1_000_000)
        for i in range(3):
            client.post(
                "/v1/transfers",
                json={"recipient_phone_number": "+2250700000002", "amount_minor": 1_000},
                headers={**sender.headers, "Idempotency-Key": f"st-pg-trx-{i}"},
            )
        first = client.get("/v1/statement?limit=2", headers=sender.headers).get_json()
        assert len(first["lines"]) == 2 and first["next_cursor"]
        rest = client.get(
            f"/v1/statement?limit=2&cursor={first['next_cursor']}", headers=sender.headers
        ).get_json()
        assert len(rest["lines"]) == 1 and rest["next_cursor"] is None
