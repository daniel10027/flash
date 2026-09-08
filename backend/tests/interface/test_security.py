"""Tests de la sécurité : JWT, require_auth, rate_limit (BE-022)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest
from flask import Flask, Response, jsonify

from flash.domain.shared.identifiers import EntityId
from flash.infrastructure.config import Settings
from flash.interface.app import create_app
from flash.interface.security.auth import current_principal, require_auth
from flash.interface.security.rate_limit import rate_limit
from flash.interface.security.tokens import TokenError, TokenReused, TokenService
from tests.support.fakes import FixedClock
from tests.support.security import (
    InMemoryAccessRevocationStore,
    InMemoryRateLimiter,
    InMemoryRefreshTokenStore,
    build_test_security,
)

USER = EntityId(UUID(int=1))
DEVICE = "device-abc"


def _service(clock: FixedClock | None = None) -> TokenService:
    return TokenService(
        secret="flash-test-secret-please-ignore-0123456789abcd",
        access_ttl_seconds=900,
        refresh_ttl_seconds=3600,
        refresh_store=InMemoryRefreshTokenStore(),
        revocation_store=InMemoryAccessRevocationStore(),
        clock=clock,
    )


class TestTokenService:
    def test_issue_and_verify_access(self) -> None:
        svc = _service()
        pair = svc.issue_pair(user_id=USER, device_id=DEVICE)
        principal = svc.verify_access(pair.access_token)
        assert principal.user_id == USER
        assert principal.device_id == DEVICE
        assert pair.access_expires_in == 900

    def test_access_token_cannot_be_used_as_refresh(self) -> None:
        svc = _service()
        pair = svc.issue_pair(user_id=USER, device_id=DEVICE)
        with pytest.raises(TokenError, match="Type de jeton"):
            svc.rotate(pair.access_token)

    def test_expired_access_token_rejected(self) -> None:
        clock = FixedClock(datetime(2026, 1, 1, tzinfo=UTC))
        svc = _service(clock)
        pair = svc.issue_pair(user_id=USER, device_id=DEVICE)
        clock.advance(seconds=901)
        with pytest.raises(TokenError, match="expiré"):
            svc.verify_access(pair.access_token)

    def test_rotation_chain_issues_fresh_pairs(self) -> None:
        svc = _service()
        first = svc.issue_pair(user_id=USER, device_id=DEVICE)
        second = svc.rotate(first.refresh_token)
        third = svc.rotate(second.refresh_token)
        assert len({first.refresh_token, second.refresh_token, third.refresh_token}) == 3
        assert svc.verify_access(third.access_token).user_id == USER

    def test_reuse_of_old_refresh_kills_device_session(self) -> None:
        svc = _service()
        first = svc.issue_pair(user_id=USER, device_id=DEVICE)
        second = svc.rotate(first.refresh_token)
        # rejouer l'ancien refresh déclenche la détection de rejeu…
        with pytest.raises(TokenReused):
            svc.rotate(first.refresh_token)
        # …et coupe toute la session de l'appareil, y compris le refresh courant.
        with pytest.raises(TokenReused):
            svc.rotate(second.refresh_token)

    def test_revoke_access_blocks_further_use(self) -> None:
        svc = _service()
        pair = svc.issue_pair(user_id=USER, device_id=DEVICE)
        principal = svc.verify_access(pair.access_token)
        svc.revoke_access(principal)
        with pytest.raises(TokenError, match="révoqué"):
            svc.verify_access(pair.access_token)

    def test_logout_revokes_access_and_refresh(self) -> None:
        svc = _service()
        pair = svc.issue_pair(user_id=USER, device_id=DEVICE)
        principal = svc.verify_access(pair.access_token)
        svc.logout(principal)
        with pytest.raises(TokenError):
            svc.verify_access(pair.access_token)
        with pytest.raises(TokenReused):
            svc.rotate(pair.refresh_token)

    def test_garbage_token_rejected(self) -> None:
        with pytest.raises(TokenError, match="invalide"):
            _service().verify_access("not-a-jwt")


@pytest.fixture
def app() -> Flask:
    bundle = build_test_security(rate_limiter=InMemoryRateLimiter())
    application = create_app(
        Settings(
            FLASH_ENV="test", FLASH_SECRET_KEY="flash-test-secret-please-ignore-0123456789abcd"
        ),
        security_bundle=bundle,
    )
    application.extensions["test_tokens"] = bundle.tokens

    @application.get("/me")
    @require_auth
    def _me() -> Response:
        p = current_principal()
        return jsonify(user_id=str(p.user_id), device_id=p.device_id)

    @application.get("/limited")
    @rate_limit(name="test", limit=2, per_seconds=60, subject="ip")
    def _limited() -> Response:
        return jsonify(ok=True)

    return application


class TestRequireAuth:
    def test_missing_header_is_401(self, app: Flask) -> None:
        resp = app.test_client().get("/me")
        assert resp.status_code == 401
        assert resp.get_json()["code"] == "UNAUTHENTICATED"

    def test_bad_token_is_401(self, app: Flask) -> None:
        resp = app.test_client().get("/me", headers={"Authorization": "Bearer nope"})
        assert resp.status_code == 401

    def test_valid_token_grants_access(self, app: Flask) -> None:
        tokens = app.extensions["test_tokens"]
        pair = tokens.issue_pair(user_id=USER, device_id=DEVICE)
        resp = app.test_client().get(
            "/me", headers={"Authorization": f"Bearer {pair.access_token}"}
        )
        assert resp.status_code == 200
        assert resp.get_json() == {"user_id": str(USER), "device_id": DEVICE}


class TestRateLimit:
    def test_requests_over_quota_get_429(self, app: Flask) -> None:
        client = app.test_client()
        assert client.get("/limited").status_code == 200
        assert client.get("/limited").status_code == 200
        blocked = client.get("/limited")
        assert blocked.status_code == 429
        assert blocked.get_json()["code"] == "RATE_LIMITED"
        assert blocked.get_json()["details"] == {"limit": 2, "per_seconds": 60}
