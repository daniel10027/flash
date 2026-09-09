"""Tests du blueprint notifications + intégration événement -> notification (BE-040)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from flask import Flask
from flask.testing import FlaskClient

from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import XOF, Money
from flash.infrastructure.config import Settings
from flash.interface.app import create_app
from tests.support.deps import build_test_deps
from tests.support.otp import RecordingOtpService
from tests.support.repositories import InMemoryUnitOfWork
from tests.support.security import build_test_security

SECRET = "flash-test-secret-please-ignore-0123456789abcd"


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


def _onboard(client: FlaskClient, phone: str, key: str) -> dict[str, str]:
    client.post(
        "/v1/auth/register",
        json={"phone_number": phone, "pin": "1397", "country": "CI"},
        headers={"Idempotency-Key": key},
    )
    tokens = client.post(
        "/v1/auth/verify-otp",
        json={"phone_number": phone, "country": "CI", "code": "000000", "device_id": "d"},
    ).get_json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _fund(uow: InMemoryUnitOfWork, phone: str, amount: int) -> None:
    from flash.domain.shared.identifiers import Msisdn

    user = uow.users.get_by_msisdn(Msisdn(phone))
    assert user is not None
    wallet = uow.wallets.list_for_user(user.id)[0]
    wallet.credit(Money(amount, XOF), datetime(2026, 1, 1, tzinfo=UTC))
    wallet.pull_events()


class TestNotificationEndpoints:
    def test_requires_auth(self, client: FlaskClient) -> None:
        assert client.get("/v1/notifications").status_code == 401

    def test_transfer_creates_notifications_for_both_parties(
        self, client: FlaskClient, uow: InMemoryUnitOfWork
    ) -> None:
        sender = _onboard(client, "+2250700000001", "notif-s-longenough")
        recipient = _onboard(client, "+2250700000002", "notif-r-longenough")
        _fund(uow, "+2250700000001", 100_000)

        r = client.post(
            "/v1/transfers",
            json={"recipient_phone_number": "+2250700000002", "amount_minor": 15_000},
            headers={**sender, "Idempotency-Key": "notif-trx-0001"},
        )
        assert r.status_code == 201

        inbox = client.get("/v1/notifications", headers=recipient).get_json()
        assert inbox["unread_count"] == 1
        assert inbox["items"][0]["kind"] == "MONEY_IN"
        assert "15 000 XOF" in inbox["items"][0]["body"]

        outbox = client.get("/v1/notifications", headers=sender).get_json()
        assert outbox["items"][0]["kind"] == "MONEY_OUT"

    def test_mark_read_and_read_all(self, client: FlaskClient, uow: InMemoryUnitOfWork) -> None:
        sender = _onboard(client, "+2250700000001", "notif2-s-longenough")
        recipient = _onboard(client, "+2250700000002", "notif2-r-longenough")
        _fund(uow, "+2250700000001", 100_000)
        for i in range(2):
            client.post(
                "/v1/transfers",
                json={"recipient_phone_number": "+2250700000002", "amount_minor": 1_000},
                headers={**sender, "Idempotency-Key": f"notif2-trx-{i}"},
            )

        inbox = client.get("/v1/notifications", headers=recipient).get_json()
        assert inbox["unread_count"] == 2
        first_id = inbox["items"][0]["id"]

        one = client.post(f"/v1/notifications/{first_id}/read", headers=recipient)
        assert one.status_code == 200 and one.get_json()["updated"] is True

        after = client.get("/v1/notifications?unread=1", headers=recipient).get_json()
        assert after["unread_count"] == 1

        allr = client.post("/v1/notifications/read-all", headers=recipient)
        assert allr.get_json()["updated"] == 1
        assert client.get("/v1/notifications", headers=recipient).get_json()["unread_count"] == 0

    def test_mark_unknown_notification_is_noop(self, client: FlaskClient) -> None:
        auth = _onboard(client, "+2250700000001", "notif3-longenough")
        resp = client.post(
            f"/v1/notifications/{EntityId('00000000-0000-4000-8000-000000000000')}/read",
            headers=auth,
        )
        assert resp.status_code == 200 and resp.get_json()["updated"] is False


class TestNotificationStream:
    def test_stream_requires_auth(self, client: FlaskClient) -> None:
        assert client.get("/v1/notifications/stream").status_code == 401

    def test_stream_emits_sse_frames_for_new_notification(
        self, client: FlaskClient, uow: InMemoryUnitOfWork
    ) -> None:
        sender = _onboard(client, "+2250700000001", "sse-s-longenough")
        recipient = _onboard(client, "+2250700000002", "sse-r-longenough")
        _fund(uow, "+2250700000001", 100_000)
        client.post(
            "/v1/transfers",
            json={"recipient_phone_number": "+2250700000002", "amount_minor": 7_000},
            headers={**sender, "Idempotency-Key": "sse-trx-0001"},
        )

        # sans Last-Event-ID le flux ne rejoue pas l'historique ; on en fournit un
        # antérieur à toute notification pour forcer le rattrapage depuis le journal.
        resp = client.get("/v1/notifications/stream", headers={**recipient, "Last-Event-ID": "0"})
        assert resp.status_code == 200
        assert resp.mimetype == "text/event-stream"
        assert resp.headers["Cache-Control"] == "no-cache"
        body = resp.get_data(as_text=True)
        assert "event: notification" in body
        assert '"kind": "MONEY_IN"' in body
        assert ": keep-alive" in body  # tick final du bus de test

    def test_stream_replays_missed_with_last_event_id(
        self, client: FlaskClient, uow: InMemoryUnitOfWork
    ) -> None:
        sender = _onboard(client, "+2250700000001", "sse2-s-longenough")
        recipient = _onboard(client, "+2250700000002", "sse2-r-longenough")
        _fund(uow, "+2250700000001", 100_000)
        for i in range(2):
            client.post(
                "/v1/transfers",
                json={"recipient_phone_number": "+2250700000002", "amount_minor": 1_000},
                headers={**sender, "Idempotency-Key": f"sse2-trx-{i}"},
            )
        inbox = client.get("/v1/notifications", headers=recipient).get_json()
        oldest_id = inbox["items"][-1]["id"]  # la plus ancienne

        resp = client.get(
            "/v1/notifications/stream",
            headers={**recipient, "Last-Event-ID": oldest_id},
        )
        body = resp.get_data(as_text=True)
        # la plus ancienne est exclue (strictement supérieur), la seconde est rejouée
        assert body.count("event: notification") == 1
        assert f"id: {oldest_id}" not in body
