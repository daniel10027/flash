"""Blueprint ``savings`` (BE-054) — plans d'épargne : ouverture, versements, clôture."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request
from pydantic import Field
from werkzeug.exceptions import BadRequest

from flash.application.savings.operations import (
    CloseSavingsPlan,
    CloseSavingsPlanCommand,
    ContributeToSavings,
    ContributeToSavingsCommand,
    ListSavingsPlans,
    ListSavingsPlansCommand,
    OpenSavingsPlan,
    OpenSavingsPlanCommand,
    WithdrawFromSavings,
    WithdrawFromSavingsCommand,
)
from flash.interface.container import deps
from flash.interface.http.schemas import ApiModel
from flash.interface.openapi import document
from flash.interface.security.auth import current_principal, require_auth
from flash.interface.security.rate_limit import rate_limit

bp = Blueprint("savings", __name__, url_prefix="/v1/savings")


def _idem_key() -> str:
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key:
        raise BadRequest("En-tête Idempotency-Key requis pour cette opération.")
    return key


def _json() -> dict[str, object]:
    return request.get_json(force=True, silent=True) or {}


_PLAN_SCHEMA = {
    "type": "object",
    "properties": {
        "plan_id": {"type": "string"},
        "name": {"type": "string"},
        "balance_minor": {"type": "integer"},
        "currency": {"type": "string"},
        "annual_rate_bps": {"type": "integer"},
        "frequency": {"type": "string", "enum": ["NONE", "WEEKLY", "MONTHLY"]},
        "contribution_minor": {"type": "integer"},
        "target_minor": {"type": ["integer", "null"]},
        "target_date": {"type": ["string", "null"]},
        "progress_bps": {"type": ["integer", "null"]},
        "accrued_interest_minor": {"type": "integer"},
        "next_contribution_at": {"type": ["string", "null"]},
        "status": {"type": "string", "enum": ["ACTIVE", "CLOSED"]},
        "created_at": {"type": "string"},
    },
}


@bp.get("/plans")
@require_auth
@document(summary="Lister mes plans d'épargne", tags=["savings"], response_schema=_PLAN_SCHEMA)
def list_plans() -> tuple[Response, int]:
    views = ListSavingsPlans(services=deps().services).execute(
        ListSavingsPlansCommand(user_id=str(current_principal().user_id))
    )
    return jsonify({"plans": [v.to_dict() for v in views]}), 200


class OpenPlanRequest(ApiModel):
    name: str = Field(min_length=1, max_length=60, examples=["Voyage 2027"])
    annual_rate_bps: int = Field(default=0, ge=0, le=2_000, examples=[350])
    frequency: str = Field(default="NONE", pattern="^(NONE|WEEKLY|MONTHLY)$")
    contribution_minor: int = Field(default=0, ge=0, examples=[10_000])
    target_minor: int | None = Field(default=None, gt=0, examples=[1_000_000])
    target_date: str | None = Field(default=None, examples=["2027-06-01T00:00:00+00:00"])


@bp.post("/plans")
@require_auth
@rate_limit(name="savings-open", limit=20, per_seconds=60, subject="user")
@document(
    summary="Ouvrir un plan d'épargne (objectif, versement programmé, taux)",
    tags=["savings"],
    status_code=201,
    request_schema=OpenPlanRequest.model_json_schema(),
    response_schema=_PLAN_SCHEMA,
)
def open_plan() -> tuple[Response, int]:
    body = OpenPlanRequest.model_validate(_json())
    view = OpenSavingsPlan(services=deps().services).execute(
        OpenSavingsPlanCommand(
            user_id=str(current_principal().user_id),
            name=body.name,
            annual_rate_bps=body.annual_rate_bps,
            frequency=body.frequency,
            contribution_minor=body.contribution_minor,
            target_minor=body.target_minor,
            target_date=body.target_date,
        )
    )
    return jsonify(view.to_dict()), 201


class MoveRequest(ApiModel):
    amount_minor: int = Field(gt=0, examples=[25_000])


@bp.post("/plans/<plan_id>/deposit")
@require_auth
@rate_limit(name="savings-deposit", limit=60, per_seconds=60, subject="user")
@document(
    summary="Verser sur un plan d'épargne",
    tags=["savings"],
    idempotent=True,
    status_code=201,
    request_schema=MoveRequest.model_json_schema(),
)
def deposit_to_plan(plan_id: str) -> tuple[Response, int]:
    body = MoveRequest.model_validate(_json())
    receipt = ContributeToSavings(services=deps().services).execute(
        ContributeToSavingsCommand(
            user_id=str(current_principal().user_id),
            plan_id=plan_id,
            amount_minor=body.amount_minor,
            idempotency_key=_idem_key(),
        )
    )
    return jsonify(receipt.to_dict()), 201


@bp.post("/plans/<plan_id>/withdraw")
@require_auth
@rate_limit(name="savings-withdraw", limit=60, per_seconds=60, subject="user")
@document(
    summary="Retirer partiellement d'un plan d'épargne (retour au portefeuille)",
    tags=["savings"],
    idempotent=True,
    status_code=201,
    request_schema=MoveRequest.model_json_schema(),
)
def withdraw_from_plan(plan_id: str) -> tuple[Response, int]:
    body = MoveRequest.model_validate(_json())
    receipt = WithdrawFromSavings(services=deps().services).execute(
        WithdrawFromSavingsCommand(
            user_id=str(current_principal().user_id),
            plan_id=plan_id,
            amount_minor=body.amount_minor,
            idempotency_key=_idem_key(),
        )
    )
    return jsonify(receipt.to_dict()), 201


@bp.post("/plans/<plan_id>/close")
@require_auth
@rate_limit(name="savings-close", limit=20, per_seconds=60, subject="user")
@document(
    summary="Clôturer un plan d'épargne (tout est rapatrié au portefeuille)",
    tags=["savings"],
    status_code=200,
)
def close_plan(plan_id: str) -> tuple[Response, int]:
    result = CloseSavingsPlan(services=deps().services).execute(
        CloseSavingsPlanCommand(user_id=str(current_principal().user_id), plan_id=plan_id)
    )
    return jsonify(result.to_dict()), 200


__all__ = ["bp"]
