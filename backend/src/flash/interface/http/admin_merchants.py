"""Blueprint back-office marchands : revue KYB (BE-069) + frais négociés par canal
(reste de BE-068). Rôles ``admin`` / ``compliance``."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request
from pydantic import Field

from flash.application.merchants.channel_fees import (
    ClearMerchantChannelFee,
    ClearMerchantChannelFeeCommand,
    GetMerchantFees,
    GetMerchantFeesCommand,
    SetMerchantChannelFee,
    SetMerchantChannelFeeCommand,
)
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


# ------------------------------------------------------------------ frais par canal
class ChannelFeeRequest(ApiModel):
    fee_bps: int = Field(ge=0, le=1000, examples=[70])


@bp.get("/<merchant_id>/fees")
@require_role("admin", "compliance")
@document(
    summary="Back-office : commission par défaut + overrides négociés par canal",
    tags=["admin"],
    secured=False,
)
def get_merchant_fees(merchant_id: str) -> tuple[Response, int]:
    view = GetMerchantFees(services=deps().services).execute(
        GetMerchantFeesCommand(merchant_id=merchant_id)
    )
    return jsonify(view.to_dict()), 200


@bp.put("/<merchant_id>/channel-fees/<channel>")
@require_role("admin", "compliance")
@document(
    summary="Back-office : fixer la commission négociée d'un canal (QR / API)",
    tags=["admin"],
    secured=False,
    request_schema=ChannelFeeRequest.model_json_schema(),
)
def set_channel_fee(merchant_id: str, channel: str) -> tuple[Response, int]:
    body = ChannelFeeRequest.model_validate(_json())
    view = SetMerchantChannelFee(services=deps().services).execute(
        SetMerchantChannelFeeCommand(
            merchant_id=merchant_id, channel=channel, fee_bps=body.fee_bps
        )
    )
    return jsonify(view.to_dict()), 200


@bp.delete("/<merchant_id>/channel-fees/<channel>")
@require_role("admin", "compliance")
@document(
    summary="Back-office : retirer l'override d'un canal (retour au tarif par défaut)",
    tags=["admin"],
    secured=False,
)
def clear_channel_fee(merchant_id: str, channel: str) -> tuple[Response, int]:
    view = ClearMerchantChannelFee(services=deps().services).execute(
        ClearMerchantChannelFeeCommand(merchant_id=merchant_id, channel=channel)
    )
    return jsonify(view.to_dict()), 200


__all__ = ["bp"]
