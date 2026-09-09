"""Blueprints marchands (BE-033) : ``merchant_bp`` (côté commerçant) et
``merchant_payments_bp`` (côté payeur)."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request
from pydantic import Field
from werkzeug.exceptions import BadRequest

from flash.application.merchants.api_keys import (
    IssueMerchantApiKey,
    IssueMerchantApiKeyCommand,
    ListMerchantApiKeys,
    ListMerchantApiKeysCommand,
    RevokeMerchantApiKey,
    RevokeMerchantApiKeyCommand,
)
from flash.application.merchants.kyb import SubmitMerchantKyb, SubmitMerchantKybCommand
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
from flash.application.merchants.poster import (
    RenderMerchantPoster,
    RenderMerchantPosterCommand,
)
from flash.application.merchants.refund import (
    RefundMerchantPayment,
    RefundMerchantPaymentCommand,
)
from flash.application.merchants.settlement import (
    ConfigureMerchantSettlement,
    ConfigureMerchantSettlementCommand,
    GetSettlementStatement,
    GetSettlementStatementCommand,
    ListMerchantSettlements,
    ListMerchantSettlementsCommand,
    SettleMerchantNow,
    SettleMerchantNowCommand,
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


# ------------------------------------------------------------------ KYB
@merchant_bp.post("/kyb")
@require_auth
@rate_limit(name="merchant-kyb", limit=10, per_seconds=60, subject="user")
@document(
    summary="Soumettre (ou re-soumettre) le dossier de vérification marchand",
    tags=["merchants"],
)
def submit_merchant_kyb() -> tuple[Response, int]:
    view = SubmitMerchantKyb(services=deps().services).execute(
        SubmitMerchantKybCommand(merchant_user_id=str(current_principal().user_id))
    )
    return jsonify(view.to_dict()), 200


# ------------------------------------------------------------------ clés d'API
class IssueApiKeyRequest(ApiModel):
    label: str = Field(default="", max_length=60, examples=["Caisse principale"])


@merchant_bp.post("/api-keys")
@require_auth
@rate_limit(name="merchant-api-key", limit=10, per_seconds=60, subject="user")
@document(
    summary="Émettre une clé d'API marchande (le secret n'est montré qu'ici)",
    tags=["merchants"],
    status_code=201,
    request_schema=IssueApiKeyRequest.model_json_schema(),
)
def issue_merchant_api_key() -> tuple[Response, int]:
    body = IssueApiKeyRequest.model_validate(_json())
    view = IssueMerchantApiKey(
        services=deps().services, vault=deps().merchant_api_key_vault
    ).execute(
        IssueMerchantApiKeyCommand(
            merchant_user_id=str(current_principal().user_id), label=body.label
        )
    )
    return jsonify(view.to_dict()), 201


@merchant_bp.get("/api-keys")
@require_auth
@document(summary="Lister les clés d'API du marchand (préfixe seul)", tags=["merchants"])
def list_merchant_api_keys() -> tuple[Response, int]:
    views = ListMerchantApiKeys(services=deps().services).execute(
        ListMerchantApiKeysCommand(merchant_user_id=str(current_principal().user_id))
    )
    return jsonify({"api_keys": [v.to_dict() for v in views]}), 200


@merchant_bp.delete("/api-keys/<key_id>")
@require_auth
@document(summary="Révoquer une clé d'API marchande", tags=["merchants"])
def revoke_merchant_api_key(key_id: str) -> tuple[Response, int]:
    view = RevokeMerchantApiKey(services=deps().services).execute(
        RevokeMerchantApiKeyCommand(
            merchant_user_id=str(current_principal().user_id), key_id=key_id
        )
    )
    return jsonify(view.to_dict()), 200


@merchant_bp.get("/poster")
@require_auth
@document(summary="Affiche imprimable (PNG) portant le QR statique du marchand", tags=["merchants"])
def merchant_poster() -> Response:
    poster = RenderMerchantPoster(
        services=deps().services, renderer=deps().merchant_poster
    ).execute(
        RenderMerchantPosterCommand(merchant_user_id=str(current_principal().user_id))
    )
    resp = Response(poster.content, mimetype=poster.media_type)
    resp.headers["Content-Disposition"] = f'inline; filename="{poster.filename}"'
    return resp


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


# ------------------------------------------------------------------ règlements
class ConfigureSettlementRequest(ApiModel):
    holder: str = Field(min_length=1, max_length=140, examples=["SARL Chez Awa"])
    iban: str = Field(min_length=8, max_length=40, examples=["CI93CI0080111301134291200589"])
    bank_name: str = Field(min_length=1, max_length=120, examples=["Ecobank CI"])
    frequency: str = Field(default="MANUAL", examples=["WEEKLY"])


@merchant_bp.put("/settlement")
@require_auth
@rate_limit(name="merchant-settlement-config", limit=20, per_seconds=60, subject="user")
@document(
    summary="Configurer le compte bancaire et la fréquence de règlement",
    tags=["merchants"],
    request_schema=ConfigureSettlementRequest.model_json_schema(),
)
def configure_settlement() -> tuple[Response, int]:
    body = ConfigureSettlementRequest.model_validate(_json())
    view = ConfigureMerchantSettlement(services=deps().services).execute(
        ConfigureMerchantSettlementCommand(
            merchant_user_id=str(current_principal().user_id),
            holder=body.holder,
            iban=body.iban,
            bank_name=body.bank_name,
            frequency=body.frequency,
        )
    )
    return jsonify(view.to_dict()), 200


@merchant_bp.post("/settlements")
@require_auth
@rate_limit(name="merchant-settle-now", limit=10, per_seconds=60, subject="user")
@document(
    summary="Déclencher immédiatement un règlement du net accumulé",
    tags=["merchants"],
    status_code=200,
)
def settle_now() -> tuple[Response, int]:
    view = SettleMerchantNow(services=deps().services, bank=deps().bank_gateway).execute(
        SettleMerchantNowCommand(merchant_user_id=str(current_principal().user_id))
    )
    if view is None:
        return jsonify({"settlement": None, "detail": "Aucun paiement à régler."}), 200
    return jsonify({"settlement": view.to_dict()}), 200


@merchant_bp.get("/settlements")
@require_auth
@document(summary="Historique des règlements du marchand", tags=["merchants"])
def list_settlements() -> tuple[Response, int]:
    views = ListMerchantSettlements(services=deps().services).execute(
        ListMerchantSettlementsCommand(merchant_user_id=str(current_principal().user_id))
    )
    return jsonify({"settlements": [v.to_dict() for v in views]}), 200


@merchant_bp.get("/settlements/<settlement_id>")
@require_auth
@document(summary="Relevé détaillé d'un règlement (paiements couverts)", tags=["merchants"])
def settlement_statement(settlement_id: str) -> tuple[Response, int]:
    statement = GetSettlementStatement(services=deps().services).execute(
        GetSettlementStatementCommand(
            merchant_user_id=str(current_principal().user_id),
            settlement_id=settlement_id,
        )
    )
    return jsonify(statement.to_dict()), 200


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
