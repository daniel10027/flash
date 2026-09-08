"""Blueprint ``statement`` — relevé / historique des opérations (BE-038)."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from flash.application.statement.queries import ListStatement, ListStatementCommand
from flash.interface.container import deps
from flash.interface.openapi import document
from flash.interface.security.auth import current_principal, require_auth

bp = Blueprint("statement", __name__, url_prefix="/v1/statement")

_LINE_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "reference": {"type": "string"},
        "kind": {"type": "string"},
        "direction": {"type": "string", "enum": ["in", "out"]},
        "amount_minor": {"type": "integer"},
        "fee_minor": {"type": "integer"},
        "currency": {"type": "string"},
        "counterparty_masked": {"type": ["string", "null"]},
        "note": {"type": ["string", "null"]},
        "occurred_at": {"type": "string"},
    },
}


@bp.get("")
@require_auth
@document(
    summary="Historique des opérations du compte (paginé par curseur)",
    tags=["statement"],
    response_schema={
        "type": "object",
        "properties": {
            "lines": {"type": "array", "items": _LINE_SCHEMA},
            "next_cursor": {"type": ["string", "null"]},
        },
    },
)
def list_statement() -> tuple[Response, int]:
    try:
        limit = int(request.args.get("limit", 20))
    except ValueError:
        limit = 20
    page = ListStatement(services=deps().services).execute(
        ListStatementCommand(
            user_id=str(current_principal().user_id),
            limit=limit,
            cursor=request.args.get("cursor"),
        )
    )
    return jsonify(page.to_dict()), 200


__all__ = ["bp"]
