"""Blueprint ``vault`` (BE-054) — le coffre et ses poches verrouillables."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request
from pydantic import Field
from werkzeug.exceptions import BadRequest

from flash.application.vault.operations import (
    CloseVaultPocket,
    CloseVaultPocketCommand,
    GetVault,
    GetVaultCommand,
    MoveFromVault,
    MoveFromVaultCommand,
    MoveToVault,
    MoveToVaultCommand,
    OpenVaultPocket,
    OpenVaultPocketCommand,
    RenameVaultPocket,
    RenameVaultPocketCommand,
)
from flash.interface.container import deps
from flash.interface.http.schemas import ApiModel
from flash.interface.openapi import document
from flash.interface.security.auth import current_principal, require_auth
from flash.interface.security.rate_limit import rate_limit

bp = Blueprint("vault", __name__, url_prefix="/v1/vault")


def _idem_key() -> str:
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key:
        raise BadRequest("En-tête Idempotency-Key requis pour cette opération.")
    return key


def _json() -> dict[str, object]:
    return request.get_json(force=True, silent=True) or {}


_POCKET_SCHEMA = {
    "type": "object",
    "properties": {
        "pocket_id": {"type": "string"},
        "name": {"type": "string"},
        "balance_minor": {"type": "integer"},
        "currency": {"type": "string"},
        "goal_minor": {"type": ["integer", "null"]},
        "progress_bps": {"type": ["integer", "null"]},
        "locked_until": {"type": ["string", "null"]},
        "created_at": {"type": "string"},
    },
}
_VAULT_SCHEMA = {
    "type": "object",
    "properties": {
        "currency": {"type": "string"},
        "vaulted_minor": {"type": "integer"},
        "pockets": {"type": "array", "items": _POCKET_SCHEMA},
    },
}


@bp.get("")
@require_auth
@document(
    summary="Consulter mon coffre et ses poches",
    tags=["vault"],
    response_schema=_VAULT_SCHEMA,
)
def get_vault() -> tuple[Response, int]:
    view = GetVault(services=deps().services).execute(
        GetVaultCommand(user_id=str(current_principal().user_id))
    )
    return jsonify(view.to_dict()), 200


class OpenPocketRequest(ApiModel):
    name: str = Field(min_length=1, max_length=60, examples=["Vacances"])
    goal_minor: int | None = Field(default=None, gt=0, examples=[500_000])
    locked_until: str | None = Field(default=None, examples=["2026-12-31T00:00:00+00:00"])


@bp.post("/pockets")
@require_auth
@rate_limit(name="vault-open", limit=30, per_seconds=60, subject="user")
@document(
    summary="Ouvrir une poche (nom, objectif et verrouillage optionnels)",
    tags=["vault"],
    status_code=201,
    request_schema=OpenPocketRequest.model_json_schema(),
    response_schema=_POCKET_SCHEMA,
)
def open_pocket() -> tuple[Response, int]:
    body = OpenPocketRequest.model_validate(_json())
    view = OpenVaultPocket(services=deps().services).execute(
        OpenVaultPocketCommand(
            user_id=str(current_principal().user_id),
            name=body.name,
            goal_minor=body.goal_minor,
            locked_until=body.locked_until,
        )
    )
    return jsonify(view.to_dict()), 201


class RenamePocketRequest(ApiModel):
    name: str = Field(min_length=1, max_length=60, examples=["Voyage 2027"])


@bp.patch("/pockets/<pocket_id>")
@require_auth
@document(
    summary="Renommer une poche",
    tags=["vault"],
    request_schema=RenamePocketRequest.model_json_schema(),
    response_schema=_POCKET_SCHEMA,
)
def rename_pocket(pocket_id: str) -> tuple[Response, int]:
    body = RenamePocketRequest.model_validate(_json())
    view = RenameVaultPocket(services=deps().services).execute(
        RenameVaultPocketCommand(
            user_id=str(current_principal().user_id), pocket_id=pocket_id, name=body.name
        )
    )
    return jsonify(view.to_dict()), 200


@bp.delete("/pockets/<pocket_id>")
@require_auth
@document(summary="Fermer une poche vide", tags=["vault"], status_code=204)
def close_pocket(pocket_id: str) -> tuple[Response, int]:
    CloseVaultPocket(services=deps().services).execute(
        CloseVaultPocketCommand(user_id=str(current_principal().user_id), pocket_id=pocket_id)
    )
    return jsonify({}), 204


class MoveRequest(ApiModel):
    amount_minor: int = Field(gt=0, examples=[20_000])


@bp.post("/pockets/<pocket_id>/deposit")
@require_auth
@rate_limit(name="vault-deposit", limit=60, per_seconds=60, subject="user")
@document(
    summary="Mettre de l'argent de côté dans une poche",
    tags=["vault"],
    idempotent=True,
    status_code=201,
    request_schema=MoveRequest.model_json_schema(),
)
def deposit_to_pocket(pocket_id: str) -> tuple[Response, int]:
    body = MoveRequest.model_validate(_json())
    receipt = MoveToVault(services=deps().services).execute(
        MoveToVaultCommand(
            user_id=str(current_principal().user_id),
            pocket_id=pocket_id,
            amount_minor=body.amount_minor,
            idempotency_key=_idem_key(),
        )
    )
    return jsonify(receipt.to_dict()), 201


@bp.post("/pockets/<pocket_id>/withdraw")
@require_auth
@rate_limit(name="vault-withdraw", limit=60, per_seconds=60, subject="user")
@document(
    summary="Reprendre de l'argent d'une poche (refusé si verrouillée)",
    tags=["vault"],
    idempotent=True,
    status_code=201,
    request_schema=MoveRequest.model_json_schema(),
)
def withdraw_from_pocket(pocket_id: str) -> tuple[Response, int]:
    body = MoveRequest.model_validate(_json())
    receipt = MoveFromVault(services=deps().services).execute(
        MoveFromVaultCommand(
            user_id=str(current_principal().user_id),
            pocket_id=pocket_id,
            amount_minor=body.amount_minor,
            idempotency_key=_idem_key(),
        )
    )
    return jsonify(receipt.to_dict()), 201


__all__ = ["bp"]
