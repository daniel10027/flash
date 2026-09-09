"""Blueprint back-office du référentiel (BE-062) — rôle ``admin`` ou ``compliance``.

Toute mutation est tracée dans le registre d'audit chaîné. ``GET /v1/admin/audit``
expose ce registre (et son contrôle d'intégrité).
"""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request
from pydantic import Field

from flash.application.reference.admin import (
    DeleteCountry,
    DeleteCountryCommand,
    DeleteOperator,
    DeleteOperatorCommand,
    ListAuditEntries,
    ListAuditEntriesCommand,
    UpsertCountry,
    UpsertCountryCommand,
    UpsertOperator,
    UpsertOperatorCommand,
)
from flash.interface.container import deps
from flash.interface.http.schemas import ApiModel
from flash.interface.openapi import document
from flash.interface.security.roles import current_actor, require_role

bp = Blueprint("admin_reference", __name__, url_prefix="/v1/admin")

_MANAGE = require_role("admin", "compliance")


def _json() -> dict[str, object]:
    return request.get_json(force=True, silent=True) or {}


# ------------------------------------------------------------------ pays
class CountryBody(ApiModel):
    name: str = Field(min_length=1, max_length=80)
    currency: str = Field(min_length=3, max_length=3)
    dialing_code: str = Field(min_length=1, max_length=6, pattern=r"^\d+$")
    timezone: str = Field(default="UTC", max_length=48)
    active: bool = True


@bp.put("/reference/countries/<code>")
@_MANAGE
@document(
    summary="Créer / mettre à jour un pays du référentiel",
    tags=["admin"],
    secured=False,
    request_schema=CountryBody.model_json_schema(),
)
def upsert_country(code: str) -> tuple[Response, int]:
    body = CountryBody.model_validate(_json())
    view = UpsertCountry(
        editor=deps().reference_editor, audit=deps().audit, clock=deps().services.clock
    ).execute(
        UpsertCountryCommand(
            actor=current_actor(),
            role=_role(),
            code=code,
            name=body.name,
            currency=body.currency,
            dialing_code=body.dialing_code,
            timezone=body.timezone,
            active=body.active,
        )
    )
    return jsonify(view.to_dict()), 200


@bp.delete("/reference/countries/<code>")
@_MANAGE
@document(summary="Supprimer un pays du référentiel", tags=["admin"], secured=False)
def delete_country(code: str) -> tuple[Response, int]:
    DeleteCountry(
        editor=deps().reference_editor, audit=deps().audit, clock=deps().services.clock
    ).execute(DeleteCountryCommand(actor=current_actor(), role=_role(), code=code))
    return jsonify({}), 204


# ------------------------------------------------------------------ opérateurs
class OperatorBody(ApiModel):
    name: str = Field(min_length=1, max_length=80)
    msisdn_prefixes: list[str] = Field(default_factory=list)
    active: bool = True


@bp.put("/reference/countries/<code>/operators/<op_code>")
@_MANAGE
@document(
    summary="Créer / mettre à jour un opérateur",
    tags=["admin"],
    secured=False,
    request_schema=OperatorBody.model_json_schema(),
)
def upsert_operator(code: str, op_code: str) -> tuple[Response, int]:
    body = OperatorBody.model_validate(_json())
    view = UpsertOperator(
        editor=deps().reference_editor, audit=deps().audit, clock=deps().services.clock
    ).execute(
        UpsertOperatorCommand(
            actor=current_actor(),
            role=_role(),
            country=code,
            code=op_code,
            name=body.name,
            msisdn_prefixes=body.msisdn_prefixes,
            active=body.active,
        )
    )
    return jsonify(view.to_dict()), 200


@bp.delete("/reference/countries/<code>/operators/<op_code>")
@_MANAGE
@document(summary="Supprimer un opérateur", tags=["admin"], secured=False)
def delete_operator(code: str, op_code: str) -> tuple[Response, int]:
    DeleteOperator(
        editor=deps().reference_editor, audit=deps().audit, clock=deps().services.clock
    ).execute(DeleteOperatorCommand(actor=current_actor(), role=_role(), code=op_code))
    return jsonify({}), 204


@bp.post("/reference/reload")
@_MANAGE
@document(
    summary="Invalider le cache du référentiel (tous les workers rechargent)",
    tags=["admin"],
    secured=False,
)
def reload_reference() -> tuple[Response, int]:
    directory = deps().reference
    bump = getattr(directory, "bump", None)
    version = int(bump()) if callable(bump) else 0
    return jsonify({"reloaded": True, "version": version}), 200


# ------------------------------------------------------------------ audit
@bp.get("/audit")
@_MANAGE
@document(summary="Registre d'audit (entrées récentes, chaînées)", tags=["admin"], secured=False)
def list_audit() -> tuple[Response, int]:
    limit = request.args.get("limit", type=int) or 100
    before = request.args.get("before_sequence", type=int)
    entries = ListAuditEntries(audit=deps().audit).execute(
        ListAuditEntriesCommand(limit=limit, before_sequence=before)
    )
    payload: dict[str, object] = {"entries": [e.to_dict() for e in entries]}
    if request.args.get("verify") == "1":
        payload["intact"] = deps().audit.verify()
    return jsonify(payload), 200


def _role() -> str:
    from flash.interface.security.roles import resolve_admin_role

    return resolve_admin_role() or "unknown"


__all__ = ["bp"]
