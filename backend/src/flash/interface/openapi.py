"""Génération de la spécification OpenAPI 3.1 et pages de documentation.

Les routes métier déclarent leur contrat via ``document(...)`` (utilisé par les
blueprints à partir de la Phase 2). ``build_spec`` assemble ces déclarations avec les
métadonnées globales, le schéma d'erreur commun et le schéma de sécurité *bearer*.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from flask import Blueprint, Flask, Response, current_app, jsonify

from flash import __version__

_ATTR = "_openapi_operation"


@dataclass(slots=True)
class Operation:
    summary: str
    tags: list[str] = field(default_factory=list)
    request_schema: dict[str, Any] | None = None
    response_schema: dict[str, Any] | None = None
    status_code: int = 200
    secured: bool = True
    idempotent: bool = False


def document[F: Callable[..., Any]](
    *,
    summary: str,
    tags: list[str] | None = None,
    request_schema: dict[str, Any] | None = None,
    response_schema: dict[str, Any] | None = None,
    status_code: int = 200,
    secured: bool = True,
    idempotent: bool = False,
) -> Callable[[F], F]:
    """Attache le contrat OpenAPI d'une opération à sa fonction de vue."""

    def decorator(fn: F) -> F:
        setattr(
            fn,
            _ATTR,
            Operation(
                summary=summary,
                tags=list(tags or []),
                request_schema=request_schema,
                response_schema=response_schema,
                status_code=status_code,
                secured=secured,
                idempotent=idempotent,
            ),
        )
        return fn

    return decorator


_ERROR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "required": ["code", "message", "details"],
    "properties": {
        "code": {"type": "string", "example": "INSUFFICIENT_FUNDS"},
        "message": {"type": "string"},
        "details": {"type": "object", "additionalProperties": True},
    },
}


def _rule_to_path(rule: str) -> str:
    # Flask "<int:id>" / "<id>" -> OpenAPI "{id}"
    out: list[str] = []
    for part in rule.split("/"):
        if part.startswith("<") and part.endswith(">"):
            out.append("{" + part.strip("<>").split(":")[-1] + "}")
        else:
            out.append(part)
    return "/".join(out)


def build_spec(app: Flask) -> dict[str, Any]:
    settings = app.extensions.get("flash_settings")
    base_url = getattr(settings, "api_base_url", "http://localhost:8000")

    paths: dict[str, Any] = {}
    for rule in app.url_map.iter_rules():
        if rule.rule.startswith(("/static", "/openapi", "/docs", "/redoc")):
            continue
        view = app.view_functions.get(rule.endpoint)
        operation: Operation | None = getattr(view, _ATTR, None)
        methods = sorted(rule.methods - {"HEAD", "OPTIONS"}) if rule.methods else []
        for method in methods:
            item = paths.setdefault(_rule_to_path(rule.rule), {})
            item[method.lower()] = _operation_object(operation, method, rule.rule)

    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Flash API",
            "version": __version__,
            "description": "API de la plateforme de monnaie électronique Flash.",
        },
        "servers": [{"url": base_url}],
        "paths": paths,
        "components": {
            "schemas": {"Error": _ERROR_SCHEMA},
            "securitySchemes": {
                "bearerAuth": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}
            },
        },
    }


def _operation_object(operation: Operation | None, method: str, rule: str) -> dict[str, Any]:
    if operation is None:
        return {
            "summary": f"{method} {rule}",
            "responses": {"200": {"description": "OK"}},
        }
    responses: dict[str, Any] = {
        str(operation.status_code): {
            "description": "Succès",
            **(
                {"content": {"application/json": {"schema": operation.response_schema}}}
                if operation.response_schema
                else {}
            ),
        },
        "4XX": {
            "description": "Erreur métier ou de validation",
            "content": {"application/json": {"schema": {"$ref": "#/components/schemas/Error"}}},
        },
    }
    obj: dict[str, Any] = {
        "summary": operation.summary,
        "tags": operation.tags,
        "responses": responses,
    }
    if operation.secured:
        obj["security"] = [{"bearerAuth": []}]
    if operation.request_schema:
        obj["requestBody"] = {
            "required": True,
            "content": {"application/json": {"schema": operation.request_schema}},
        }
    if operation.idempotent:
        obj["parameters"] = [
            {
                "name": "Idempotency-Key",
                "in": "header",
                "required": True,
                "schema": {"type": "string", "minLength": 8, "maxLength": 255},
            }
        ]
    return obj


_SWAGGER_HTML = """<!doctype html><html><head><meta charset="utf-8">
<title>Flash API — Swagger UI</title>
<link rel="stylesheet" href="https://unpkg.com/swagger-ui-dist@5/swagger-ui.css">
</head><body><div id="swagger-ui"></div>
<script src="https://unpkg.com/swagger-ui-dist@5/swagger-ui-bundle.js"></script>
<script>window.onload=()=>SwaggerUIBundle({url:"/openapi.json",dom_id:"#swagger-ui"});</script>
</body></html>"""

_REDOC_HTML = """<!doctype html><html><head><meta charset="utf-8"><title>Flash API — ReDoc</title>
</head><body><redoc spec-url="/openapi.json"></redoc>
<script src="https://cdn.redoc.ly/redoc/latest/bundles/redoc.standalone.js"></script>
</body></html>"""


def register_docs(app: Flask) -> None:
    bp = Blueprint("openapi", __name__)

    @bp.get("/openapi.json")
    def _spec() -> Response:
        return jsonify(build_spec(current_app))

    @bp.get("/docs")
    def _swagger() -> str:
        return _SWAGGER_HTML

    @bp.get("/redoc")
    def _redoc() -> str:
        return _REDOC_HTML

    app.register_blueprint(bp)


def dump_spec(path: str = "docs/api/openapi.json") -> str:
    from flash.interface.app import create_app

    spec = build_spec(create_app())
    import pathlib

    target = pathlib.Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(spec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return str(target)


__all__ = ["Operation", "build_spec", "document", "dump_spec", "register_docs"]
