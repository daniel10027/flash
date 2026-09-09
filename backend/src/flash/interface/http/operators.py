"""Blueprints interop opérateurs (BE-065 → BE-067) : côté client + webhook réseau."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request
from pydantic import Field
from werkzeug.exceptions import BadRequest

from flash.application.operators.callbacks import (
    HandleOperatorCallback,
    OperatorCallbackCommand,
)
from flash.application.operators.operations import (
    ListOperatorTransfers,
    ListOperatorTransfersCommand,
    SendToOperatorAccount,
    SendToOperatorAccountCommand,
    TopUpFromOperator,
    TopUpFromOperatorCommand,
)
from flash.interface.container import deps
from flash.interface.http.schemas import ApiModel
from flash.interface.openapi import document
from flash.interface.security.auth import current_principal, require_auth
from flash.interface.security.operator_webhook import require_operator_webhook
from flash.interface.security.rate_limit import rate_limit

bp = Blueprint("operators", __name__, url_prefix="/v1/operators")
webhook_bp = Blueprint("operator_webhook", __name__, url_prefix="/v1/operators")


def _idem_key() -> str:
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key:
        raise BadRequest("En-tête Idempotency-Key requis pour cette opération.")
    return key


def _json() -> dict[str, object]:
    return request.get_json(force=True, silent=True) or {}


class MoveRequest(ApiModel):
    operator: str = Field(min_length=2, max_length=32)
    msisdn: str = Field(min_length=8, max_length=20)
    amount_minor: int = Field(gt=0, examples=[50_000])


@bp.get("/transfers")
@require_auth
@document(summary="Mes transferts opérateurs (envois / rechargements)", tags=["operators"])
def list_transfers() -> tuple[Response, int]:
    lines = ListOperatorTransfers(services=deps().services).execute(
        ListOperatorTransfersCommand(user_id=str(current_principal().user_id))
    )
    return jsonify({"transfers": [line.to_dict() for line in lines]}), 200


@bp.post("/payouts")
@require_auth
@rate_limit(name="operator-payout", limit=30, per_seconds=60, subject="user")
@document(
    summary="Envoyer de l'argent vers un compte opérateur (interop sortante)",
    tags=["operators"],
    idempotent=True,
    status_code=201,
    request_schema=MoveRequest.model_json_schema(),
)
def send_payout() -> tuple[Response, int]:
    body = MoveRequest.model_validate(_json())
    receipt = SendToOperatorAccount(
        services=deps().services,
        gateway=deps().operator_gateway,
        reference=deps().reference,
        pricing=deps().pricing,
        limits=deps().limits,
        kyc=deps().kyc,
    ).execute(
        SendToOperatorAccountCommand(
            user_id=str(current_principal().user_id),
            operator=body.operator,
            msisdn=body.msisdn,
            amount_minor=body.amount_minor,
            idempotency_key=_idem_key(),
        )
    )
    return jsonify(receipt.to_dict()), 201


@bp.post("/topups")
@require_auth
@rate_limit(name="operator-topup", limit=30, per_seconds=60, subject="user")
@document(
    summary="Recharger son portefeuille depuis un compte opérateur (interop entrante)",
    tags=["operators"],
    idempotent=True,
    status_code=201,
    request_schema=MoveRequest.model_json_schema(),
)
def request_topup() -> tuple[Response, int]:
    body = MoveRequest.model_validate(_json())
    receipt = TopUpFromOperator(
        services=deps().services,
        gateway=deps().operator_gateway,
        reference=deps().reference,
        pricing=deps().pricing,
        limits=deps().limits,
        kyc=deps().kyc,
    ).execute(
        TopUpFromOperatorCommand(
            user_id=str(current_principal().user_id),
            operator=body.operator,
            msisdn=body.msisdn,
            amount_minor=body.amount_minor,
            idempotency_key=_idem_key(),
        )
    )
    return jsonify(receipt.to_dict()), 201


class CallbackRequest(ApiModel):
    reference: str = Field(min_length=4, max_length=64)
    status: str = Field(pattern="^(SUCCEEDED|FAILED)$")
    external_ref: str | None = Field(default=None, max_length=64)
    reason: str | None = Field(default=None, max_length=120)


@webhook_bp.post("/<operator>/callbacks")
@require_operator_webhook
@document(
    summary="Callback opérateur : résolution d'un transfert (signé, idempotent)",
    tags=["operators"],
    secured=False,
    request_schema=CallbackRequest.model_json_schema(),
)
def operator_callback(operator: str) -> tuple[Response, int]:
    body = CallbackRequest.model_validate(_json())
    result = HandleOperatorCallback(services=deps().services).execute(
        OperatorCallbackCommand(
            operator=operator,
            reference=body.reference,
            status=body.status,
            external_ref=body.external_ref,
            reason=body.reason,
        )
    )
    return jsonify(result.to_dict()), 200


__all__ = ["bp", "webhook_bp"]
