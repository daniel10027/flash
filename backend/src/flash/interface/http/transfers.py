"""Blueprint ``transfers`` — transfert P2P (BE-031)."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request
from pydantic import Field
from werkzeug.exceptions import BadRequest

from flash.application.transfers.reverse import CancelTransfer, CancelTransferCommand
from flash.application.transfers.send_p2p import SendP2PTransfer, SendP2PTransferCommand
from flash.interface.container import deps
from flash.interface.http.schemas import ApiModel
from flash.interface.openapi import document
from flash.interface.security.auth import current_principal, require_auth
from flash.interface.security.rate_limit import rate_limit

bp = Blueprint("transfers", __name__, url_prefix="/v1/transfers")


class TransferRequest(ApiModel):
    recipient_phone_number: str = Field(min_length=6, max_length=24, examples=["+2250700000002"])
    amount_minor: int = Field(gt=0, examples=[10_000])
    country: str | None = Field(default=None, min_length=2, max_length=2)
    note: str | None = Field(default=None, max_length=140)


_RECEIPT_SCHEMA = {
    "type": "object",
    "properties": {
        "transfer_id": {"type": "string"},
        "reference": {"type": "string"},
        "amount_minor": {"type": "integer"},
        "fee_minor": {"type": "integer"},
        "total_minor": {"type": "integer"},
        "currency": {"type": "string"},
        "recipient_masked": {"type": "string"},
        "sender_balance_after_minor": {"type": "integer"},
        "occurred_at": {"type": "string"},
    },
}


@bp.post("")
@require_auth
@rate_limit(name="transfer", limit=30, per_seconds=60, subject="user")
@document(
    summary="Envoyer de l'argent à un autre compte Flash",
    tags=["transfers"],
    idempotent=True,
    status_code=201,
    request_schema=TransferRequest.model_json_schema(),
    response_schema=_RECEIPT_SCHEMA,
)
def send_transfer() -> tuple[Response, int]:
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key:
        raise BadRequest("En-tête Idempotency-Key requis pour cette opération.")
    body = TransferRequest.model_validate(request.get_json(force=True, silent=True) or {})
    receipt = SendP2PTransfer(
        services=deps().services,
        pricing=deps().pricing,
        limits=deps().limits,
        kyc=deps().kyc,
    ).execute(
        SendP2PTransferCommand(
            sender_user_id=str(current_principal().user_id),
            recipient_phone_number=body.recipient_phone_number,
            amount_minor=body.amount_minor,
            idempotency_key=key,
            country=body.country,
            note=body.note,
        )
    )
    return jsonify(receipt.to_dict()), 201


@bp.post("/<transfer_id>/cancel")
@require_auth
@rate_limit(name="transfer-cancel", limit=10, per_seconds=600, subject="user")
@document(
    summary="Annuler un transfert récent (contre-passation)",
    tags=["transfers"],
    idempotent=True,
    status_code=200,
)
def cancel_transfer(transfer_id: str) -> tuple[Response, int]:
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key:
        raise BadRequest("En-tête Idempotency-Key requis pour cette opération.")
    receipt = CancelTransfer(services=deps().services, window=deps().reversal_window).execute(
        CancelTransferCommand(
            actor_user_id=str(current_principal().user_id),
            transfer_id=transfer_id,
            idempotency_key=key,
        )
    )
    return jsonify(receipt.to_dict()), 200


__all__ = ["bp"]
