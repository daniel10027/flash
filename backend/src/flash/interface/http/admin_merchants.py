"""Blueprint back-office marchands (BE-069) : revue KYB. Rôles ``admin`` / ``compliance``."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request
from pydantic import Field

from flash.application.merchants.kyb import ReviewMerchantKyb, ReviewMerchantKybCommand
from flash.interface.container import deps
from flash.interface.http.schemas import ApiModel
from flash.interface.openapi import document
from flash.interface.security.roles import current_actor, require_role

bp = Blueprint("admin_merchants", __name__, url_prefix="/v1/admin/merchants")


def _json() -> dict[str, object]:
    return request.get_json(force=True, silent=True) or {}


class ReviewKybRequest(ApiModel):
    decision: str = Field(examples=["approve", "reject"])
    reason: str = Field(default="", max_length=200)


@bp.post("/<merchant_id>/kyb")
@require_role("admin", "compliance")
@document(
    summary="Back-office : approuver ou rejeter la vérification (KYB) d'un marchand",
    tags=["admin"],
    secured=False,
    request_schema=ReviewKybRequest.model_json_schema(),
)
def review_merchant_kyb(merchant_id: str) -> tuple[Response, int]:
    body = ReviewKybRequest.model_validate(_json())
    view = ReviewMerchantKyb(services=deps().services).execute(
        ReviewMerchantKybCommand(
            merchant_id=merchant_id,
            reviewer=current_actor(),
            approve=body.decision == "approve",
            reason=body.reason,
        )
    )
    return jsonify(view.to_dict()), 200


__all__ = ["bp"]
