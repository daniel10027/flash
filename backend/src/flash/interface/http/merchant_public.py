"""API marchande publique ``/merchant/v1/…`` (BE-071).

Authentifiée par clé d'API (``Authorization: Bearer mk_…`` ou en-tête ``X-Merchant-Key``).
Surface volontairement réduite : créer une demande de paiement, lire son état, la
rembourser, lister les encaissements. Les webhooks signés notifient le back-end du
marchand des paiements encaissés / remboursés.
"""

from __future__ import annotations

from flask import Blueprint, Response, g, jsonify, request
from pydantic import Field
from werkzeug.exceptions import BadRequest, Unauthorized

from flash.application.merchants.operations import (
    CreateMerchantCharge,
    CreateMerchantChargeCommand,
    ListMerchantPayments,
    ListMerchantPaymentsCommand,
)
from flash.application.merchants.public_api import (
    AuthenticateMerchantApiKey,
    AuthenticateMerchantApiKeyCommand,
    GetMerchantChargeStatus,
    GetMerchantChargeStatusCommand,
    MerchantPrincipal,
)
from flash.application.merchants.refund import (
    RefundMerchantPayment,
    RefundMerchantPaymentCommand,
)
from flash.domain.shared.errors import InvalidInput, MerchantApiKeyInvalid
from flash.interface.container import deps
from flash.interface.http.schemas import ApiModel
from flash.interface.openapi import document

bp = Blueprint("merchant_public", __name__, url_prefix="/merchant/v1")


def _presented_secret() -> str:
    header = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[7:].strip()
    return request.headers.get("X-Merchant-Key", "").strip()


def _merchant() -> MerchantPrincipal:
    principal = getattr(g, "merchant_principal", None)
    if principal is None:
        secret = _presented_secret()
        if not secret:
            raise Unauthorized("Clé d'API marchande requise.")
        try:
            principal = AuthenticateMerchantApiKey(
                services=deps().services, vault=deps().merchant_api_key_vault
            ).execute(AuthenticateMerchantApiKeyCommand(presented_secret=secret))
        except MerchantApiKeyInvalid as exc:
            raise Unauthorized(str(exc)) from exc
        g.merchant_principal = principal
    return principal


def _idem_key() -> str:
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key:
        raise BadRequest("En-tête Idempotency-Key requis pour cette opération.")
    return key


def _json() -> dict[str, object]:
    return request.get_json(force=True, silent=True) or {}


class CreateChargeBody(ApiModel):
    amount_minor: int = Field(gt=0, examples=[25_000])
    reference: str = Field(min_length=1, max_length=80, examples=["Commande #4821"])
    ttl_minutes: int = Field(default=60, ge=1, le=1440)


@bp.post("/charges")
@document(
    summary="API marchande : créer une demande de paiement (QR dynamique)",
    tags=["merchant-api"],
    secured=False,
    status_code=201,
    request_schema=CreateChargeBody.model_json_schema(),
)
def create_charge() -> tuple[Response, int]:
    principal = _merchant()
    body = CreateChargeBody.model_validate(_json())
    view = CreateMerchantCharge(services=deps().services).execute(
        CreateMerchantChargeCommand(
            merchant_user_id=principal.merchant_user_id,
            amount_minor=body.amount_minor,
            reference=body.reference,
            ttl_minutes=body.ttl_minutes,
        )
    )
    return jsonify(view.to_dict()), 201


@bp.get("/charges/<charge_id>")
@document(
    summary="API marchande : état d'une demande de paiement",
    tags=["merchant-api"],
    secured=False,
)
def charge_status(charge_id: str) -> tuple[Response, int]:
    principal = _merchant()
    view = GetMerchantChargeStatus(services=deps().services).execute(
        GetMerchantChargeStatusCommand(
            merchant_id=principal.merchant_id, charge_id=charge_id
        )
    )
    return jsonify(view.to_dict()), 200


@bp.post("/charges/<charge_id>/refund")
@document(
    summary="API marchande : rembourser le paiement d'une demande",
    tags=["merchant-api"],
    secured=False,
    idempotent=True,
)
def refund_charge(charge_id: str) -> tuple[Response, int]:
    principal = _merchant()
    status = GetMerchantChargeStatus(services=deps().services).execute(
        GetMerchantChargeStatusCommand(
            merchant_id=principal.merchant_id, charge_id=charge_id
        )
    )
    if status.payment_id is None:
        raise InvalidInput("Cette demande n'a pas de paiement à rembourser.")
    receipt = RefundMerchantPayment(
        services=deps().services, window=deps().reversal_window
    ).execute(
        RefundMerchantPaymentCommand(
            merchant_user_id=principal.merchant_user_id,
            payment_id=status.payment_id,
            idempotency_key=_idem_key(),
        )
    )
    return jsonify(receipt.to_dict()), 200


@bp.get("/payments")
@document(
    summary="API marchande : encaissements récents",
    tags=["merchant-api"],
    secured=False,
)
def list_payments() -> tuple[Response, int]:
    principal = _merchant()
    lines = ListMerchantPayments(services=deps().services).execute(
        ListMerchantPaymentsCommand(merchant_user_id=principal.merchant_user_id)
    )
    return jsonify({"payments": [line.to_dict() for line in lines]}), 200


__all__ = ["bp"]
