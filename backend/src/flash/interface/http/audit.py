"""Blueprint registre d'audit consultable (BE-078). Rôles ``admin`` / ``compliance``.

``GET /v1/admin/audit`` — liste filtrée (``actor``, ``action``, ``resource_type``,
``resource_id``, ``start``, ``end``, ``limit``, ``before_sequence``), plus récentes
d'abord ; ``?verify=1`` joint le contrôle d'intégrité.
``GET /v1/admin/audit/verify`` — contrôle d'intégrité de toute la chaîne (localise la
première rupture).
"""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from flash.application.audit.registry import (
    QueryAuditLog,
    QueryAuditLogCommand,
    VerifyAuditChain,
    VerifyAuditChainCommand,
)
from flash.interface.container import deps
from flash.interface.openapi import document
from flash.interface.security.roles import require_role

bp = Blueprint("audit", __name__, url_prefix="/v1/admin/audit")

_MANAGE = require_role("admin", "compliance")


@bp.get("")
@_MANAGE
@document(
    summary="Registre d'audit : consultation filtrée (qui/quoi/ressource/période)",
    tags=["admin"],
    secured=False,
)
def list_audit() -> tuple[Response, int]:
    page = QueryAuditLog(audit=deps().audit).execute(
        QueryAuditLogCommand(
            actor=request.args.get("actor"),
            action=request.args.get("action"),
            resource_type=request.args.get("resource_type"),
            resource_id=request.args.get("resource_id"),
            start=request.args.get("start"),
            end=request.args.get("end"),
            limit=request.args.get("limit", default=100, type=int),
            before_sequence=request.args.get("before_sequence", type=int),
            verify=request.args.get("verify") == "1",
        )
    )
    return jsonify(page.to_dict()), 200


@bp.get("/verify")
@_MANAGE
@document(
    summary="Registre d'audit : contrôle d'intégrité de la chaîne chaînée par hachage",
    tags=["admin"],
    secured=False,
)
def verify_audit() -> tuple[Response, int]:
    report = VerifyAuditChain(audit=deps().audit).execute(VerifyAuditChainCommand())
    return jsonify(report.to_dict()), 200 if report.intact else 409


__all__ = ["bp"]
