"""Fabrique de l'application Flask.

``create_app`` assemble : configuration, journalisation JSON, identifiant de requête,
gestion centralisée des erreurs (``DomainError`` -> HTTP), en-têtes CORS, points de
santé. Les blueprints métier sont enregistrés au fur et à mesure (BE-041, etc.).
"""

from __future__ import annotations

import uuid
from typing import Any

import structlog
from flask import Flask, Response, g, jsonify, request
from pydantic import ValidationError
from werkzeug.exceptions import HTTPException

from flash.application.auth.tokens import TokenError
from flash.domain.shared.errors import DomainError
from flash.infrastructure.config import Settings, get_settings
from flash.interface.container import Deps, build_deps, register_deps
from flash.interface.errors import status_for, to_payload
from flash.interface.http import auth as auth_routes
from flash.interface.http import cash as cash_routes
from flash.interface.http import kyc as kyc_routes
from flash.interface.http import merchants as merchant_routes
from flash.interface.http import payment_requests as payment_request_routes
from flash.interface.http import phones as phones_routes
from flash.interface.http import statement as statement_routes
from flash.interface.http import transfers as transfers_routes
from flash.interface.http import wallets as wallets_routes
from flash.interface.logging import configure_logging
from flash.interface.openapi import register_docs
from flash.interface.security.auth import Unauthenticated
from flash.interface.security.wiring import SecurityBundle, build_security, register_security

_log = structlog.get_logger("flash.http")


def create_app(
    settings: Settings | None = None,
    *,
    security_bundle: SecurityBundle | None = None,
    deps: Deps | None = None,
) -> Flask:
    settings = settings or get_settings()
    configure_logging(settings.log_level, json_output=settings.is_production)

    if settings.is_production and settings.secret_key.startswith("dev-insecure"):
        raise RuntimeError("FLASH_SECRET_KEY par défaut interdit en production.")

    app = Flask(__name__)
    app.config.update(
        SECRET_KEY=settings.secret_key,
        JSON_SORT_KEYS=False,
        PROPAGATE_EXCEPTIONS=False,
    )
    app.extensions["flash_settings"] = settings
    bundle = security_bundle or build_security(settings)
    register_security(app, bundle)
    register_deps(app, deps or build_deps(settings, tokens=bundle.tokens))

    _register_request_context(app, settings)
    _register_error_handlers(app)
    _register_health(app)
    register_docs(app)
    app.register_blueprint(auth_routes.bp)
    app.register_blueprint(phones_routes.bp)
    app.register_blueprint(wallets_routes.bp)
    app.register_blueprint(transfers_routes.bp)
    app.register_blueprint(payment_request_routes.bp)
    app.register_blueprint(statement_routes.bp)
    app.register_blueprint(statement_routes.receipts_bp)
    app.register_blueprint(cash_routes.withdrawals_bp)
    app.register_blueprint(cash_routes.agent_bp)
    app.register_blueprint(kyc_routes.bp)
    app.register_blueprint(kyc_routes.admin_bp)
    app.register_blueprint(merchant_routes.merchant_bp)
    app.register_blueprint(merchant_routes.merchant_payments_bp)
    return app


def _register_request_context(app: Flask, settings: Settings) -> None:
    allowed_origins = set(settings.cors_origins)

    @app.before_request
    def _assign_request_id() -> None:
        g.request_id = request.headers.get("X-Request-ID") or uuid.uuid4().hex
        structlog.contextvars.bind_contextvars(
            request_id=g.request_id, method=request.method, path=request.path
        )

    @app.after_request
    def _finalise(response: Response) -> Response:
        response.headers["X-Request-ID"] = g.get("request_id", "")
        origin = request.headers.get("Origin")
        if origin and origin in allowed_origins:
            response.headers["Access-Control-Allow-Origin"] = origin
            response.headers["Vary"] = "Origin"
            response.headers["Access-Control-Allow-Credentials"] = "true"
            response.headers["Access-Control-Allow-Headers"] = (
                "Authorization, Content-Type, Idempotency-Key, X-Request-ID"
            )
            response.headers["Access-Control-Allow-Methods"] = (
                "GET, POST, PUT, PATCH, DELETE, OPTIONS"
            )
        _log.info("request", status=response.status_code)
        structlog.contextvars.clear_contextvars()
        return response


def _register_error_handlers(app: Flask) -> None:
    @app.errorhandler(DomainError)
    def _handle_domain_error(error: DomainError) -> tuple[Response, int]:
        status = status_for(error)
        if status >= 500:  # pragma: no cover - défensif
            _log.error("domain_error", code=error.code)
        return jsonify(to_payload(error)), status

    @app.errorhandler(Unauthenticated)
    def _handle_unauthenticated(error: Unauthenticated) -> tuple[Response, int]:
        return jsonify({"code": "UNAUTHENTICATED", "message": error.message, "details": {}}), 401

    @app.errorhandler(TokenError)
    def _handle_token_error(error: TokenError) -> tuple[Response, int]:
        return jsonify(
            {"code": "INVALID_TOKEN", "message": str(error) or "Jeton invalide.", "details": {}}
        ), 401

    @app.errorhandler(ValidationError)
    def _handle_validation_error(error: ValidationError) -> tuple[Response, int]:
        fields = [
            {"field": ".".join(str(p) for p in e["loc"]), "error": e["msg"]} for e in error.errors()
        ]
        return jsonify(
            {
                "code": "VALIDATION_ERROR",
                "message": "Requête invalide.",
                "details": {"fields": fields},
            }
        ), 422

    @app.errorhandler(HTTPException)
    def _handle_http_exception(error: HTTPException) -> tuple[Response, int]:
        payload: dict[str, Any] = {
            "code": error.name.upper().replace(" ", "_"),
            "message": error.description or error.name,
            "details": {},
        }
        return jsonify(payload), error.code or 500

    @app.errorhandler(Exception)
    def _handle_unexpected(error: Exception) -> tuple[Response, int]:
        _log.exception("unhandled_exception")
        payload: dict[str, Any] = {
            "code": "INTERNAL_ERROR",
            "message": "Une erreur interne est survenue.",
            "details": {},
        }
        return jsonify(payload), 500


def _register_health(app: Flask) -> None:
    @app.get("/health")
    def _health() -> Response:
        return jsonify(status="ok")

    @app.get("/health/ready")
    def _ready() -> tuple[Response, int]:
        from sqlalchemy import text

        from flash.infrastructure.db.engine import get_engine

        checks: dict[str, str] = {}
        try:
            with get_engine().connect() as conn:
                conn.execute(text("SELECT 1"))
            checks["database"] = "ok"
        except Exception as exc:
            checks["database"] = f"error: {exc.__class__.__name__}"

        healthy = all(v == "ok" for v in checks.values())
        status_code = 200 if healthy else 503
        return jsonify(status="ok" if healthy else "degraded", checks=checks), status_code


__all__ = ["create_app"]
