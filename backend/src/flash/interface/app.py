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
from werkzeug.exceptions import HTTPException

from flash.domain.shared.errors import DomainError
from flash.infrastructure.config import Settings, get_settings
from flash.interface.errors import status_for, to_payload
from flash.interface.logging import configure_logging

_log = structlog.get_logger("flash.http")


def create_app(settings: Settings | None = None) -> Flask:
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

    _register_request_context(app, settings)
    _register_error_handlers(app)
    _register_health(app)
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
