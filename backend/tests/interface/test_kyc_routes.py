"""Tests du blueprint kyc : soumission client + revue back-office (BE-029)."""

from __future__ import annotations

import base64
from typing import Any

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
PHONE = "+2250700000001"
PNG = base64.b64encode(b"\x89PNG\r\n\x1a\n" + b"x" * 32).decode()
ADMIN_HEADERS = {
    "X-Admin-Key": "test-admin-key",
    "X-Admin-Reviewer": "00000000-0000-0000-0000-0000000000aa",
}


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


@pytest.fixture
def app(uow: InMemoryUnitOfWork) -> Flask:
    bundle = build_test_security()
    deps = build_test_deps(uow=uow, otp=RecordingOtpService(), bundle=bundle)
    return create_app(
        Settings(FLASH_ENV="test", FLASH_SECRET_KEY=SECRET),
        security_bundle=bundle,
        deps=deps,
    )


@pytest.fixture
def client(app: Flask) -> FlaskClient:
    return app.test_client()


@pytest.fixture
def auth(client: FlaskClient) -> dict[str, str]:
    client.post(
        "/v1/auth/register",
        json={"phone_number": PHONE, "pin": "1397", "country": "CI"},
        headers={"Idempotency-Key": "kyc-setup-key"},
    )
    tokens = client.post(
        "/v1/auth/verify-otp",
        json={"phone_number": PHONE, "country": "CI", "code": "000000", "device_id": "d1"},
    ).get_json()
    return {"Authorization": f"Bearer {tokens['access_token']}"}


def _submit(client: FlaskClient, auth: dict[str, str], key: str = "kyc-submit-1") -> dict[str, Any]:
    body: dict[str, Any] = client.post(
        "/v1/kyc/submissions",
        headers={**auth, "Idempotency-Key": key},
        json={
            "target_tier": 1,
            "documents": [
                {"kind": "ID_FRONT", "content_base64": PNG, "content_type": "image/png"},
                {"kind": "SELFIE", "content_base64": PNG, "content_type": "image/png"},
            ],
        },
    ).get_json()
    return body


class TestKycEndpoints:
    def test_requires_auth(self, client: FlaskClient) -> None:
        assert client.get("/v1/kyc/status").status_code == 401

    def test_submit_then_status_then_approve_flow(
        self, client: FlaskClient, auth: dict[str, str]
    ) -> None:
        submitted = _submit(client, auth)
        assert submitted["status"] == "PENDING"
        case_id = submitted["case_id"]

        status = client.get("/v1/kyc/status", headers=auth).get_json()
        assert status["kyc_tier"] == 0
        assert status["pending_case"]["case_id"] == case_id

        resp = client.post(
            f"/v1/admin/kyc/submissions/{case_id}/review",
            headers=ADMIN_HEADERS,
            json={"approve": True},
        )
        assert resp.status_code == 200
        assert resp.get_json()["status"] == "APPROVED"

        after = client.get("/v1/kyc/status", headers=auth).get_json()
        assert after["kyc_tier"] == 1
        assert after["pending_case"] is None

    def test_submit_requires_idempotency_key(
        self, client: FlaskClient, auth: dict[str, str]
    ) -> None:
        resp = client.post(
            "/v1/kyc/submissions",
            headers=auth,
            json={
                "target_tier": 1,
                "documents": [
                    {"kind": "ID_FRONT", "content_base64": PNG, "content_type": "image/png"},
                    {"kind": "SELFIE", "content_base64": PNG, "content_type": "image/png"},
                ],
            },
        )
        assert resp.status_code == 400

    def test_missing_required_document_is_422(
        self, client: FlaskClient, auth: dict[str, str]
    ) -> None:
        resp = client.post(
            "/v1/kyc/submissions",
            headers={**auth, "Idempotency-Key": "kyc-missing-doc"},
            json={
                "target_tier": 1,
                "documents": [
                    {"kind": "ID_FRONT", "content_base64": PNG, "content_type": "image/png"}
                ],
            },
        )
        assert resp.status_code == 422

    def test_withdraw_removes_pending_case(self, client: FlaskClient, auth: dict[str, str]) -> None:
        case_id = _submit(client, auth)["case_id"]
        resp = client.post(f"/v1/kyc/submissions/{case_id}/withdraw", headers=auth)
        assert resp.status_code == 204
        assert client.get("/v1/kyc/status", headers=auth).get_json()["pending_case"] is None

    def test_review_without_admin_key_is_forbidden(
        self, client: FlaskClient, auth: dict[str, str]
    ) -> None:
        case_id = _submit(client, auth)["case_id"]
        resp = client.post(f"/v1/admin/kyc/submissions/{case_id}/review", json={"approve": True})
        assert resp.status_code == 403

    def test_review_with_wrong_admin_key_is_forbidden(
        self, client: FlaskClient, auth: dict[str, str]
    ) -> None:
        case_id = _submit(client, auth)["case_id"]
        resp = client.post(
            f"/v1/admin/kyc/submissions/{case_id}/review",
            headers={"X-Admin-Key": "nope"},
            json={"approve": True},
        )
        assert resp.status_code == 403

    def test_list_submissions_returns_history(
        self, client: FlaskClient, auth: dict[str, str]
    ) -> None:
        case_id = _submit(client, auth)["case_id"]
        client.post(f"/v1/kyc/submissions/{case_id}/withdraw", headers=auth)
        body = client.get("/v1/kyc/submissions", headers=auth).get_json()
        assert [c["status"] for c in body["submissions"]] == ["WITHDRAWN"]


class TestKycBackOfficeQueue:
    def test_queue_lists_pending_and_detail_carries_documents(
        self, client: FlaskClient, auth: dict[str, str]
    ) -> None:
        case_id = _submit(client, auth)["case_id"]

        queue = client.get("/v1/admin/kyc/submissions", headers=ADMIN_HEADERS)
        assert queue.status_code == 200
        assert [c["case_id"] for c in queue.get_json()["submissions"]] == [case_id]

        detail = client.get(
            f"/v1/admin/kyc/submissions/{case_id}", headers=ADMIN_HEADERS
        ).get_json()
        assert detail["case_id"] == case_id
        assert {d["kind"] for d in detail["documents"]} == {"ID_FRONT", "SELFIE"}

    def test_queue_filters_by_status(
        self, client: FlaskClient, auth: dict[str, str]
    ) -> None:
        case_id = _submit(client, auth)["case_id"]
        client.post(f"/v1/kyc/submissions/{case_id}/withdraw", headers=auth)

        assert client.get(
            "/v1/admin/kyc/submissions", headers=ADMIN_HEADERS
        ).get_json()["submissions"] == []
        withdrawn = client.get(
            "/v1/admin/kyc/submissions?status=WITHDRAWN", headers=ADMIN_HEADERS
        ).get_json()
        assert [c["case_id"] for c in withdrawn["submissions"]] == [case_id]

    def test_document_bytes_are_served_without_cache(
        self, client: FlaskClient, auth: dict[str, str]
    ) -> None:
        case_id = _submit(client, auth)["case_id"]
        resp = client.get(
            f"/v1/admin/kyc/submissions/{case_id}/documents/ID_FRONT", headers=ADMIN_HEADERS
        )
        assert resp.status_code == 200
        assert resp.mimetype == "image/png"
        assert resp.headers["Cache-Control"] == "no-store"
        assert resp.data == base64.b64decode(PNG)

    def test_unknown_document_kind_is_422(
        self, client: FlaskClient, auth: dict[str, str]
    ) -> None:
        case_id = _submit(client, auth)["case_id"]
        resp = client.get(
            f"/v1/admin/kyc/submissions/{case_id}/documents/ID_BACK", headers=ADMIN_HEADERS
        )
        assert resp.status_code == 422

    def test_queue_requires_admin_key(self, client: FlaskClient) -> None:
        assert client.get("/v1/admin/kyc/submissions").status_code == 403
        assert (
            client.get("/v1/admin/kyc/submissions", headers={"X-Admin-Key": "nope"}).status_code
            == 403
        )
