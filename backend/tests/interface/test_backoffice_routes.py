"""Routes back-office comptes & support (BE-075) : lectures, gel, reversal, notes, tickets, RBAC."""

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


def _register(client: FlaskClient, phone: str, key: str) -> dict[str, str]:
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


def _admin(key: str = ADMIN_KEY) -> dict[str, str]:
    return {"X-Admin-Key": key}


class TestBackofficeRead:
    def test_search_and_detail(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, uow, _deps = app_and_uow
        client = app.test_client()
        _register(client, A_PHONE, "backoffice-user-a")
        user = uow.users.get_by_msisdn(Msisdn(A_PHONE))
        assert user is not None

        found = client.get(
            "/v1/admin/accounts", query_string={"q": A_PHONE}, headers=_admin()
        )
        assert found.status_code == 200
        assert found.get_json()["user_id"] == str(user.id)

        detail = client.get(f"/v1/admin/accounts/{user.id}", headers=_admin())
        assert detail.status_code == 200
        assert detail.get_json()["account"]["status"] == "ACTIVE"

    def test_read_requires_backoffice_role(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, _uow, _deps = app_and_uow
        assert app.test_client().get("/v1/admin/accounts?q=x").status_code == 403

    def test_transactions_list(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, uow, _deps = app_and_uow
        client = app.test_client()
        sender_auth = _register(client, A_PHONE, "backoffice-sender")
        _register(client, B_PHONE, "backoffice-recipient")
        sender = uow.users.get_by_msisdn(Msisdn(A_PHONE))
        assert sender is not None
        wallet = uow.wallets.list_for_user(sender.id)[0]
        wallet.credit(Money(100_000, XOF), FixedClock().now())
        wallet.pull_events()
        client.post(
            "/v1/transfers",
            headers={**sender_auth, "Idempotency-Key": "backoffice-transfer-1"},
            json={"recipient_phone_number": B_PHONE, "amount_minor": 10_000},
        )
        resp = client.get(
            f"/v1/admin/accounts/{sender.id}/transactions", headers=_admin()
        )
        assert resp.status_code == 200
        assert len(resp.get_json()["transactions"]) == 1


class TestBackofficeActions:
    def test_freeze_unfreeze_flow_and_audit(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, uow, _deps = app_and_uow
        client = app.test_client()
        _register(client, A_PHONE, "backoffice-freeze-user")
        user = uow.users.get_by_msisdn(Msisdn(A_PHONE))
        assert user is not None

        frozen = client.post(
            f"/v1/admin/accounts/{user.id}/freeze",
            headers=_admin(COMPLIANCE_KEY),
            json={"frozen": True, "reason": "signalement fraude"},
        )
        assert frozen.status_code == 200 and frozen.get_json()["status"] == "FROZEN"

        thawed = client.post(
            f"/v1/admin/accounts/{user.id}/freeze",
            headers=_admin(COMPLIANCE_KEY),
            json={"frozen": False},
        )
        assert thawed.status_code == 200 and thawed.get_json()["status"] == "ACTIVE"

        audit = client.get("/v1/admin/audit", headers=_admin()).get_json()
        actions = [e["action"] for e in audit["entries"]]
        assert "account.freeze" in actions and "account.unfreeze" in actions

    def test_force_reversal_requires_finance_role(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, _uow, _deps = app_and_uow
        resp = app.test_client().post(
            "/v1/admin/transactions/force-reversal",
            headers=_admin(COMPLIANCE_KEY),
            json={"transaction_id": "00000000-0000-4000-8000-000000000001", "reason": "x"},
        )
        assert resp.status_code == 403

    def test_force_reversal_end_to_end(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, uow, _deps = app_and_uow
        client = app.test_client()
        sender_auth = _register(client, A_PHONE, "backoffice-rev-sender")
        _register(client, B_PHONE, "backoffice-rev-recipient")
        sender = uow.users.get_by_msisdn(Msisdn(A_PHONE))
        assert sender is not None
        wallet = uow.wallets.list_for_user(sender.id)[0]
        wallet.credit(Money(100_000, XOF), FixedClock().now())
        wallet.pull_events()
        client.post(
            "/v1/transfers",
            headers={**sender_auth, "Idempotency-Key": "backoffice-rev-transfer"},
            json={"recipient_phone_number": B_PHONE, "amount_minor": 10_000},
        )
        [txn] = uow.ledger.transactions
        resp = client.post(
            "/v1/admin/transactions/force-reversal",
            headers=_admin(),
            json={"transaction_id": str(txn.id), "reason": "double débit"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["amount_minor"] == 10_000

    def test_notes_and_tickets(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, uow, _deps = app_and_uow
        client = app.test_client()
        _register(client, A_PHONE, "backoffice-notes-user")
        user = uow.users.get_by_msisdn(Msisdn(A_PHONE))
        assert user is not None

        note = client.post(
            f"/v1/admin/accounts/{user.id}/notes",
            headers=_admin(),
            json={"body": "Client rappelé, litige clos"},
        )
        assert note.status_code == 201
        notes = client.get(
            f"/v1/admin/accounts/{user.id}/notes", headers=_admin()
        ).get_json()
        assert len(notes["notes"]) == 1

        ticket = client.post(
            "/v1/admin/tickets",
            headers=_admin(),
            json={"user_id": str(user.id), "subject": "Retrait bloqué"},
        )
        assert ticket.status_code == 201
        ticket_id = ticket.get_json()["ticket_id"]

        moved = client.post(
            f"/v1/admin/tickets/{ticket_id}/status",
            headers=_admin(COMPLIANCE_KEY),
            json={"status": "RESOLVED"},
        )
        assert moved.status_code == 200 and moved.get_json()["status"] == "RESOLVED"

        listed = client.get(
            "/v1/admin/tickets", query_string={"status": "RESOLVED"}, headers=_admin()
        ).get_json()
        assert [t["ticket_id"] for t in listed["tickets"]] == [ticket_id]

    def test_ticket_open_requires_role(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, _uow, _deps = app_and_uow
        resp = app.test_client().post(
            "/v1/admin/tickets", json={"user_id": "x" * 10, "subject": "s"}
        )
        assert resp.status_code == 403
