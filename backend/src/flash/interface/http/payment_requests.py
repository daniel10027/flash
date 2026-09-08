"""Blueprint ``payment_requests`` — demandes de paiement entre utilisateurs (BE-032)."""

from __future__ import annotations

from typing import Literal

from flask import Blueprint, Response, jsonify, request
from pydantic import Field
from werkzeug.exceptions import BadRequest

from flash.application.payments.requests import (
    AcceptPaymentRequest,
    AcceptPaymentRequestCommand,
    CancelPaymentRequest,
    CancelPaymentRequestCommand,
    CreatePaymentRequest,
    CreatePaymentRequestCommand,
    DeclinePaymentRequest,
    DeclinePaymentRequestCommand,
    ListPaymentRequests,
    ListPaymentRequestsCommand,
)
from flash.application.transfers.send_p2p import SendP2PTransfer
from flash.interface.container import deps
from flash.interface.http.schemas import ApiModel
from flash.interface.openapi import document
from flash.interface.security.auth import current_principal, require_auth
from flash.interface.security.rate_limit import rate_limit

bp = Blueprint("payment_requests", __name__, url_prefix="/v1/payment-requests")


def _idem_key() -> str:
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key:
        raise BadRequest("En-tête Idempotency-Key requis pour cette opération.")
    return key


def _json() -> dict[str, object]:
    return request.get_json(force=True, silent=True) or {}


def _transfers() -> SendP2PTransfer:
    return SendP2PTransfer(
        services=deps().services, pricing=deps().pricing, limits=deps().limits, kyc=deps().kyc
    )


class CreatePaymentRequestBody(ApiModel):
    payer_phone_number: str = Field(min_length=6, max_length=24, examples=["+2250700000002"])
    amount_minor: int = Field(gt=0, examples=[15_000])
    note: str | None = Field(default=None, max_length=140)
    country: str | None = Field(default=None, min_length=2, max_length=2)


@bp.post("")
@require_auth
@rate_limit(name="payment-request-create", limit=30, per_seconds=60, subject="user")
@document(
    summary="Réclamer un paiement à un autre compte Flash",
    tags=["payment-requests"],
    idempotent=True,
    status_code=201,
    request_schema=CreatePaymentRequestBody.model_json_schema(),
)
def create_payment_request() -> tuple[Response, int]:
    body = CreatePaymentRequestBody.model_validate(_json())
    view = CreatePaymentRequest(services=deps().services).execute(
        CreatePaymentRequestCommand(
            requester_user_id=str(current_principal().user_id),
            payer_phone_number=body.payer_phone_number,
            amount_minor=body.amount_minor,
            idempotency_key=_idem_key(),
            note=body.note,
            country=body.country,
        )
    )
    return jsonify(view.to_dict()), 201


@bp.get("")
@require_auth
@document(
    summary="Lister ses demandes de paiement (reçues ou émises)",
    tags=["payment-requests"],
)
def list_payment_requests() -> tuple[Response, int]:
    raw = request.args.get("box", "incoming")
    box: Literal["incoming", "outgoing"] = "outgoing" if raw == "outgoing" else "incoming"
    views = ListPaymentRequests(services=deps().services).execute(
        ListPaymentRequestsCommand(user_id=str(current_principal().user_id), box=box)
    )
    return jsonify({"box": box, "requests": [v.to_dict() for v in views]}), 200


@bp.post("/<request_id>/accept")
@require_auth
@rate_limit(name="payment-request-accept", limit=30, per_seconds=60, subject="user")
@document(
    summary="Accepter une demande de paiement (déclenche le transfert)",
    tags=["payment-requests"],
    status_code=200,
)
def accept_payment_request(request_id: str) -> tuple[Response, int]:
    result = AcceptPaymentRequest(services=deps().services, transfers=_transfers()).execute(
        AcceptPaymentRequestCommand(
            payer_user_id=str(current_principal().user_id), request_id=request_id
        )
    )
    return jsonify(
        {"request": result.request.to_dict(), "transfer": result.transfer.to_dict()}
    ), 200


@bp.post("/<request_id>/decline")
@require_auth
@document(summary="Refuser une demande de paiement reçue", tags=["payment-requests"])
def decline_payment_request(request_id: str) -> tuple[Response, int]:
    view = DeclinePaymentRequest(services=deps().services).execute(
        DeclinePaymentRequestCommand(
            payer_user_id=str(current_principal().user_id), request_id=request_id
        )
    )
    return jsonify(view.to_dict()), 200


@bp.post("/<request_id>/cancel")
@require_auth
@document(
    summary="Annuler une demande de paiement que l'on a émise",
    tags=["payment-requests"],
    status_code=204,
)
def cancel_payment_request(request_id: str) -> tuple[Response, int]:
    CancelPaymentRequest(services=deps().services).execute(
        CancelPaymentRequestCommand(
            requester_user_id=str(current_principal().user_id), request_id=request_id
        )
    )
    return Response(status=204), 204


__all__ = ["bp"]
