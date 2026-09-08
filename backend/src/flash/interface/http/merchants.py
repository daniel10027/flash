"""Blueprints marchands (BE-033) : ``merchant_bp`` (côté commerçant) et
``merchant_payments_bp`` (côté payeur)."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request
from pydantic import Field
from werkzeug.exceptions import BadRequest

from flash.application.merchants.operations import (
    CreateMerchantCharge,
    CreateMerchantChargeCommand,
    GetMerchantQr,
    GetMerchantQrCommand,
    ListMerchantPayments,
    ListMerchantPaymentsCommand,
    PayMerchant,
    PayMerchantCommand,
)
from flash.application.merchants.refund import (
    RefundMerchantPayment,
    RefundMerchantPaymentCommand,
)
from flash.interface.container import deps
from flash.interface.http.schemas import ApiModel
from flash.interface.openapi import document
from flash.interface.security.auth import current_principal, require_auth
from flash.interface.security.rate_limit import rate_limit

merchant_bp = Blueprint("merchant", __name__, url_prefix="/v1/merchant")
merchant_payments_bp = Blueprint("merchant_payments", __name__, url_prefix="/v1/merchant-payments")


def _idem_key() -> str:
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key:
        raise BadRequest("En-tête Idempotency-Key requis pour cette opération.")
    return key


def _json() -> dict[str, object]:
    return request.get_json(force=True, silent=True) or {}


# ------------------------------------------------------------------ commerçant
@merchant_bp.get("/qr")
@require_auth
@document(summary="QR statique du marchand (montant saisi par le client)", tags=["merchants"])
def merchant_qr() -> tuple[Response, int]:
    view = GetMerchantQr(services=deps().services).execute(
        GetMerchantQrCommand(merchant_user_id=str(current_principal().user_id))
    )
    return jsonify(view.to_dict()), 200


class CreateChargeRequest(ApiModel):
    amount_minor: int = Field(gt=0, examples=[25_000])
    reference: str = Field(min_length=1, max_length=80, examples=["Table 4"])
    ttl_minutes: int = Field(default=60, ge=1, le=1440)


@merchant_bp.post("/charges")
@require_auth
@rate_limit(name="merchant-charge", limit=120, per_seconds=60, subject="user")
@document(
    summary="Créer un QR dynamique (montant + référence + expiration)",
    tags=["merchants"],
    status_code=201,
    request_schema=CreateChargeRequest.model_json_schema(),
)
def create_charge() -> tuple[Response, int]:
    body = CreateChargeRequest.model_validate(_json())
    view = CreateMerchantCharge(services=deps().services).execute(
        CreateMerchantChargeCommand(
            merchant_user_id=str(current_principal().user_id),
            amount_minor=body.amount_minor,
            reference=body.reference,
            ttl_minutes=body.ttl_minutes,
        )
    )
    return jsonify(view.to_dict()), 201


@merchant_bp.get("/payments")
@require_auth
@document(summary="Encaissements du marchand", tags=["merchants"])
def merchant_payments() -> tuple[Response, int]:
    lines = ListMerchantPayments(services=deps().services).execute(
        ListMerchantPaymentsCommand(merchant_user_id=str(current_principal().user_id))
    )
    return jsonify({"payments": [line.to_dict() for line in lines]}), 200


@merchant_bp.post("/payments/<payment_id>/refund")
@require_auth
@rate_limit(name="merchant-refund", limit=30, per_seconds=60, subject="user")
@document(
    summary="Rembourser un paiement encaissé (contre-passation)",
    tags=["merchants"],
    idempotent=True,
    status_code=200,
)
def refund_merchant_payment(payment_id: str) -> tuple[Response, int]:
    receipt = RefundMerchantPayment(
        services=deps().services, window=deps().reversal_window
    ).execute(
        RefundMerchantPaymentCommand(
            merchant_user_id=str(current_principal().user_id),
            payment_id=payment_id,
            idempotency_key=_idem_key(),
        )
    )
    return jsonify(receipt.to_dict()), 200


# ------------------------------------------------------------------ payeur
class PayMerchantRequest(ApiModel):
    merchant_id: str = Field(min_length=8, max_length=64)
    amount_minor: int | None = Field(default=None, gt=0, examples=[25_000])
    charge_id: str | None = Field(default=None, min_length=8, max_length=64)


@merchant_payments_bp.post("")
@require_auth
@rate_limit(name="merchant-pay", limit=60, per_seconds=60, subject="user")
@document(
    summary="Payer un marchand (QR statique avec montant, ou QR dynamique)",
    tags=["merchants"],
    idempotent=True,
    status_code=201,
    request_schema=PayMerchantRequest.model_json_schema(),
)
def pay_merchant() -> tuple[Response, int]:
    body = PayMerchantRequest.model_validate(_json())
    receipt = PayMerchant(services=deps().services, limits=deps().limits, kyc=deps().kyc).execute(
        PayMerchantCommand(
            payer_user_id=str(current_principal().user_id),
            merchant_id=body.merchant_id,
            idempotency_key=_idem_key(),
            amount_minor=body.amount_minor,
            charge_id=body.charge_id,
        )
    )
    return jsonify(receipt.to_dict()), 201


__all__ = ["merchant_bp", "merchant_payments_bp"]
