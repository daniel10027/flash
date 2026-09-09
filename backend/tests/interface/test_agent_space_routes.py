"""Routes BE-072/073/074 : espace agent (/v1/agent) + back-office hiérarchie + job."""

from __future__ import annotations

from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient

from flash.application.cash.operations import EnrollAgent, EnrollAgentCommand
from flash.domain.agent.agent import Agent
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
AGENT_PHONE = "+2250700000007"
CLIENT_PHONE = "+2250700000003"


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


def _agent(
    app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any],
) -> tuple[FlaskClient, dict[str, str], str]:
    app, uow, deps = app_and_uow
    client = app.test_client()
    auth = _login(client, AGENT_PHONE, "agent-space-registration")
    user = uow.users.get_by_msisdn(Msisdn(AGENT_PHONE))
    assert user is not None
    view = EnrollAgent(services=deps.services).execute(
        EnrollAgentCommand(
            user_id=str(user.id), float_cap_minor=5_000_000, initial_float_minor=1_000_000
        )
    )
    return client, auth, view.agent_id


class TestAgentSpace:
    def test_overview_reflects_float_and_commission(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        client, auth, agent_id = _agent(app_and_uow)
        body = client.get("/v1/agent", headers=auth).get_json()
        assert body["agent_id"] == agent_id
        assert body["float_available_minor"] == 1_000_000
        assert body["commission_owed_minor"] == 0

    def test_float_topup_and_withdraw(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        client, auth, _agent_id = _agent(app_and_uow)
        up = client.post(
            "/v1/agent/float/topup",
            headers={**auth, "Idempotency-Key": "agent-space-topup-1"},
            json={"amount_minor": 500_000},
        )
        assert up.status_code == 201
        assert up.get_json()["float_available_after_minor"] == 1_500_000

        down = client.post(
            "/v1/agent/float/withdraw",
            headers={**auth, "Idempotency-Key": "agent-space-withdraw-1"},
            json={"amount_minor": 200_000},
        )
        assert down.status_code == 201
        assert down.get_json()["float_available_after_minor"] == 1_300_000

    def test_commission_payout(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        client, auth, agent_id = _agent(app_and_uow)
        _app, uow, _deps = app_and_uow
        agent = uow.agents.get(EntityId(agent_id))
        assert agent is not None
        agent.accrue_commission(Money(4_000, XOF), FixedClock().now())
        agent.pull_events()
        uow.agents.save(agent)

        resp = client.post("/v1/agent/commission/payout", headers=auth, json={})
        assert resp.status_code == 200
        assert resp.get_json()["commission_owed_minor"] == 0

    def test_operations_list(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        client, auth, _agent_id = _agent(app_and_uow)
        client_auth = _login(client, CLIENT_PHONE, "agent-space-client-registration")
        assert client_auth  # client existe
        resp = client.post(
            "/v1/agent/deposits",
            headers={**auth, "Idempotency-Key": "agent-space-deposit-1"},
            json={"client_phone_number": CLIENT_PHONE, "amount_minor": 25_000},
        )
        assert resp.status_code == 201
        ops = client.get("/v1/agent/operations", headers=auth).get_json()
        assert len(ops["operations"]) == 1
        assert ops["operations"][0]["type"] == "DEPOSIT"

    def test_customer_lookup(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        client, auth, _agent_id = _agent(app_and_uow)
        _login(client, CLIENT_PHONE, "agent-space-lookup-client")
        resp = client.get(
            "/v1/agent/customers",
            query_string={"msisdn": CLIENT_PHONE, "country": "CI"},
            headers=auth,
        )
        assert resp.status_code == 200
        assert resp.get_json()["msisdn_masked"] != CLIENT_PHONE

    def test_customer_lookup_requires_msisdn(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        client, auth, _agent_id = _agent(app_and_uow)
        assert client.get("/v1/agent/customers", headers=auth).status_code == 400

    def test_space_requires_auth(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, _uow, _deps = app_and_uow
        assert app.test_client().get("/v1/agent").status_code == 401

    def test_overview_for_non_agent_is_404(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, _uow, _deps = app_and_uow
        client = app.test_client()
        auth = _login(client, CLIENT_PHONE, "agent-space-plain-user")
        assert client.get("/v1/agent", headers=auth).status_code == 404


class TestBackOfficeAndJob:
    def test_attach_master_and_job(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        client, _auth, agent_id = _agent(app_and_uow)
        _app, uow, _deps = app_and_uow
        master = Agent(
            id=EntityId("00000000-0000-4000-8000-0000000000aa"),
            user_id=EntityId("00000000-0000-4000-8000-0000000000ab"),
            currency=XOF,
            float_available=Money(0, XOF),
            float_cap=Money(1_000_000, XOF),
            commission_bps=50,
            created_at=FixedClock().now(),
        )
        uow.agents.add(master)

        attach = client.post(
            f"/v1/admin/agents/{agent_id}/master",
            headers={"X-Admin-Key": ADMIN_KEY},
            json={"master_agent_id": str(master.id)},
        )
        assert attach.status_code == 200
        assert attach.get_json()["parent_agent_id"] == str(master.id)

        agent = uow.agents.get(EntityId(agent_id))
        assert agent is not None
        agent.accrue_commission(Money(9_000, XOF), FixedClock().now())
        agent.pull_events()
        uow.agents.save(agent)

        run = client.post(
            "/v1/admin/jobs/agents/commissions", headers={"X-Admin-Key": ADMIN_KEY}
        )
        assert run.status_code == 200
        assert run.get_json()["paid"] == 1

    def test_attach_master_requires_role(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        client, _auth, agent_id = _agent(app_and_uow)
        resp = client.post(
            f"/v1/admin/agents/{agent_id}/master",
            json={"master_agent_id": str(agent_id)},
        )
        assert resp.status_code == 403

    def test_commission_job_requires_admin(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, _uow, _deps = app_and_uow
        assert (
            app.test_client().post("/v1/admin/jobs/agents/commissions").status_code == 403
        )
