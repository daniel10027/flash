"""Routes BE-069 : KYB marchand (self + back-office), clés d'API, affiche imprimable."""

from __future__ import annotations

from typing import Any

import pytest
from flask import Flask
from flask.testing import FlaskClient

from flash.application.merchants.operations import EnrollMerchant, EnrollMerchantCommand
from flash.domain.shared.identifiers import Msisdn
from flash.infrastructure.config import Settings
from flash.interface.app import create_app
from tests.support.deps import build_test_deps
from tests.support.otp import RecordingOtpService
from tests.support.repositories import InMemoryUnitOfWork
from tests.support.security import build_test_security

SECRET = "flash-test-secret-please-ignore-0123456789abcd"
ADMIN_KEY = "test-admin-key"
COMPLIANCE_KEY = "test-compliance-key"
MERCHANT_PHONE = "+2250700000009"


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


def _merchant_client(
    app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any],
) -> tuple[FlaskClient, dict[str, str], str]:
    app, uow, deps = app_and_uow
    client = app.test_client()
    client.post(
        "/v1/auth/register",
        json={"phone_number": MERCHANT_PHONE, "pin": "1397", "country": "CI"},
        headers={"Idempotency-Key": "merchant-registration-1"},
    )
    tokens = client.post(
        "/v1/auth/verify-otp",
        json={
            "phone_number": MERCHANT_PHONE,
            "country": "CI",
            "code": "000000",
            "device_id": "d1",
        },
    ).get_json()
    auth = {"Authorization": f"Bearer {tokens['access_token']}"}
    user = uow.users.get_by_msisdn(Msisdn(MERCHANT_PHONE))
    assert user is not None
    view = EnrollMerchant(services=deps.services).execute(
        EnrollMerchantCommand(user_id=str(user.id), display_name="Chez Awa")
    )
    return client, auth, view.merchant_id


class TestKybFlow:
    def test_submit_then_admin_approves(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        client, auth, merchant_id = _merchant_client(app_and_uow)

        submitted = client.post("/v1/merchant/kyb", headers=auth)
        assert submitted.status_code == 200
        assert submitted.get_json()["kyb_status"] == "PENDING"

        approved = client.post(
            f"/v1/admin/merchants/{merchant_id}/kyb",
            headers={"X-Admin-Key": COMPLIANCE_KEY},
            json={"decision": "approve"},
        )
        assert approved.status_code == 200
        assert approved.get_json()["kyb_status"] == "APPROVED"

        qr = client.get("/v1/merchant/qr", headers=auth).get_json()
        assert qr["kyb_status"] == "APPROVED"

    def test_admin_rejects_with_reason(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        client, _auth, merchant_id = _merchant_client(app_and_uow)
        resp = client.post(
            f"/v1/admin/merchants/{merchant_id}/kyb",
            headers={"X-Admin-Key": ADMIN_KEY},
            json={"decision": "reject", "reason": "RCCM manquant"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["kyb_status"] == "REJECTED"
        assert body["kyb_reason"] == "RCCM manquant"

    def test_admin_review_requires_role(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        client, _auth, merchant_id = _merchant_client(app_and_uow)
        resp = client.post(
            f"/v1/admin/merchants/{merchant_id}/kyb", json={"decision": "approve"}
        )
        assert resp.status_code == 403

    def test_reject_without_reason_is_422(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        client, _auth, merchant_id = _merchant_client(app_and_uow)
        resp = client.post(
            f"/v1/admin/merchants/{merchant_id}/kyb",
            headers={"X-Admin-Key": ADMIN_KEY},
            json={"decision": "reject"},
        )
        assert resp.status_code == 422


class TestApiKeys:
    def test_issue_list_revoke(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        client, auth, _merchant_id = _merchant_client(app_and_uow)

        issued = client.post("/v1/merchant/api-keys", headers=auth, json={"label": "Caisse"})
        assert issued.status_code == 201
        body = issued.get_json()
        assert body["secret"].startswith("mk_")
        assert body["label"] == "Caisse"
        key_id = body["key_id"]

        listed = client.get("/v1/merchant/api-keys", headers=auth).get_json()
        assert len(listed["api_keys"]) == 1
        assert "secret" not in listed["api_keys"][0]

        revoked = client.delete(f"/v1/merchant/api-keys/{key_id}", headers=auth)
        assert revoked.status_code == 200
        assert revoked.get_json()["revoked"] is True

    def test_revoke_unknown_key_is_422(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        client, auth, _merchant_id = _merchant_client(app_and_uow)
        resp = client.delete(
            "/v1/merchant/api-keys/00000000-0000-4000-8000-000000000123", headers=auth
        )
        assert resp.status_code == 422

    def test_api_keys_require_auth(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, _uow, _deps = app_and_uow
        assert app.test_client().get("/v1/merchant/api-keys").status_code == 401


class TestPoster:
    def test_poster_returns_png(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        client, auth, _merchant_id = _merchant_client(app_and_uow)
        resp = client.get("/v1/merchant/poster", headers=auth)
        assert resp.status_code == 200
        assert resp.mimetype == "image/png"
        assert resp.data.startswith(b"\x89PNG")
        assert "attachment" not in resp.headers.get("Content-Disposition", "")

    def test_poster_requires_auth(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, _uow, _deps = app_and_uow
        assert app.test_client().get("/v1/merchant/poster").status_code == 401

    def test_poster_for_non_merchant_is_404(
        self, app_and_uow: tuple[Flask, InMemoryUnitOfWork, Any]
    ) -> None:
        app, _uow, _deps = app_and_uow
        client = app.test_client()
        client.post(
            "/v1/auth/register",
            json={"phone_number": "+2250700000001", "pin": "1397", "country": "CI"},
            headers={"Idempotency-Key": "plain-user-registration"},
        )
        tokens = client.post(
            "/v1/auth/verify-otp",
            json={
                "phone_number": "+2250700000001",
                "country": "CI",
                "code": "000000",
                "device_id": "d1",
            },
        ).get_json()
        auth = {"Authorization": f"Bearer {tokens['access_token']}"}
        assert client.get("/v1/merchant/poster", headers=auth).status_code == 404
