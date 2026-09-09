"""Blueprint back-office grille tarifaire & plafonds (reste de BE-062).

Rôle ``admin`` ou ``compliance``. Chaque mutation est tracée dans le registre d'audit
chaîné. Les règles sont relues directement en base à chaque opération monétaire.
"""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request
from pydantic import Field

from flash.application.reference.tariffs_admin import (
    DeleteLimitRule,
    DeleteLimitRuleCommand,
    DeletePricingRule,
    DeletePricingRuleCommand,
    ListLimitRules,
    ListPricingRules,
    UpsertLimitRule,
    UpsertLimitRuleCommand,
    UpsertPricingRule,
    UpsertPricingRuleCommand,
)
from flash.interface.container import deps
from flash.interface.http.schemas import ApiModel
from flash.interface.openapi import document
from flash.interface.security.roles import current_actor, require_role

bp = Blueprint("admin_tariffs", __name__, url_prefix="/v1/admin/reference")

_MANAGE = require_role("admin", "compliance")


def _json() -> dict[str, object]:
    return request.get_json(force=True, silent=True) or {}


def _role() -> str:
    from flash.interface.security.roles import resolve_admin_role

    return resolve_admin_role() or "unknown"


# ------------------------------------------------------------------ grille tarifaire
class PricingRuleBody(ApiModel):
    currency: str = Field(min_length=3, max_length=3)
    percent_bps: int = Field(default=0, ge=0, le=10_000)
    fixed_fee_minor: int | None = Field(default=None, ge=0)
    min_fee_minor: int | None = Field(default=None, ge=0)
    max_fee_minor: int | None = Field(default=None, ge=0)
    rounding: str = Field(default="HALF_UP", max_length=16)


@bp.get("/pricing")
@_MANAGE
@document(summary="Grille tarifaire : lister les règles", tags=["admin"], secured=False)
def list_pricing() -> tuple[Response, int]:
    rules = ListPricingRules(editor=deps().pricing_editor).execute()
    return jsonify({"rules": [r.to_dict() for r in rules]}), 200


@bp.put("/pricing/<code>/<operation>")
@_MANAGE
@document(
    summary="Grille tarifaire : créer / mettre à jour une règle (pays, opération)",
    tags=["admin"],
    secured=False,
    request_schema=PricingRuleBody.model_json_schema(),
)
def upsert_pricing(code: str, operation: str) -> tuple[Response, int]:
    body = PricingRuleBody.model_validate(_json())
    view = UpsertPricingRule(
        editor=deps().pricing_editor, audit=deps().audit, clock=deps().services.clock
    ).execute(
        UpsertPricingRuleCommand(
            actor=current_actor(),
            role=_role(),
            country=code,
            operation=operation,
            currency=body.currency,
            percent_bps=body.percent_bps,
            fixed_fee_minor=body.fixed_fee_minor,
            min_fee_minor=body.min_fee_minor,
            max_fee_minor=body.max_fee_minor,
            rounding=body.rounding,
        )
    )
    return jsonify(view.to_dict()), 200


@bp.delete("/pricing/<code>/<operation>")
@_MANAGE
@document(summary="Grille tarifaire : supprimer une règle", tags=["admin"], secured=False)
def delete_pricing(code: str, operation: str) -> tuple[Response, int]:
    DeletePricingRule(
        editor=deps().pricing_editor, audit=deps().audit, clock=deps().services.clock
    ).execute(
        DeletePricingRuleCommand(
            actor=current_actor(), role=_role(), country=code, operation=operation
        )
    )
    return jsonify({}), 204


# ------------------------------------------------------------------ plafonds
class LimitRuleBody(ApiModel):
    currency: str = Field(min_length=3, max_length=3)
    per_tx_minor: int | None = Field(default=None, ge=0)
    daily_minor: int | None = Field(default=None, ge=0)
    monthly_minor: int | None = Field(default=None, ge=0)
    balance_max_minor: int | None = Field(default=None, ge=0)


@bp.get("/limits")
@_MANAGE
@document(summary="Plafonds : lister les règles", tags=["admin"], secured=False)
def list_limits() -> tuple[Response, int]:
    rules = ListLimitRules(editor=deps().limit_editor).execute()
    return jsonify({"rules": [r.to_dict() for r in rules]}), 200


@bp.put("/limits/<code>/<int:tier>/<operation>")
@_MANAGE
@document(
    summary="Plafonds : créer / mettre à jour une règle (pays, palier KYC, opération)",
    tags=["admin"],
    secured=False,
    request_schema=LimitRuleBody.model_json_schema(),
)
def upsert_limit(code: str, tier: int, operation: str) -> tuple[Response, int]:
    body = LimitRuleBody.model_validate(_json())
    view = UpsertLimitRule(
        editor=deps().limit_editor, audit=deps().audit, clock=deps().services.clock
    ).execute(
        UpsertLimitRuleCommand(
            actor=current_actor(),
            role=_role(),
            country=code,
            kyc_tier=tier,
            operation=operation,
            currency=body.currency,
            per_tx_minor=body.per_tx_minor,
            daily_minor=body.daily_minor,
            monthly_minor=body.monthly_minor,
            balance_max_minor=body.balance_max_minor,
        )
    )
    return jsonify(view.to_dict()), 200


@bp.delete("/limits/<code>/<int:tier>/<operation>")
@_MANAGE
@document(summary="Plafonds : supprimer une règle", tags=["admin"], secured=False)
def delete_limit(code: str, tier: int, operation: str) -> tuple[Response, int]:
    DeleteLimitRule(
        editor=deps().limit_editor, audit=deps().audit, clock=deps().services.clock
    ).execute(
        DeleteLimitRuleCommand(
            actor=current_actor(),
            role=_role(),
            country=code,
            kyc_tier=tier,
            operation=operation,
        )
    )
    return jsonify({}), 204


__all__ = ["bp"]
