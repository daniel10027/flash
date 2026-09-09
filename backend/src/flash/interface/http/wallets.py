"""Blueprint ``wallets`` — consultation des portefeuilles du compte (BE-030)."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify

from flash.application.wallet.queries import (
    GetWallet,
    GetWalletCommand,
    ListWallets,
    ListWalletsCommand,
)
from flash.interface.container import deps
from flash.interface.openapi import document
from flash.interface.security.auth import current_principal, require_auth

bp = Blueprint("wallets", __name__, url_prefix="/v1/wallets")

_WALLET_SCHEMA = {
    "type": "object",
    "properties": {
        "id": {"type": "string"},
        "currency": {"type": "string"},
        "status": {"type": "string"},
        "available_minor": {"type": "integer"},
        "reserved_minor": {"type": "integer"},
        "vaulted_minor": {"type": "integer"},
        "saved_minor": {"type": "integer"},
        "balance_minor": {"type": "integer"},
        "created_at": {"type": "string"},
    },
}


@bp.get("")
@require_auth
@document(summary="Lister mes portefeuilles", tags=["wallets"], response_schema=_WALLET_SCHEMA)
def list_wallets() -> tuple[Response, int]:
    views = ListWallets(services=deps().services).execute(
        ListWalletsCommand(user_id=str(current_principal().user_id))
    )
    return jsonify({"wallets": [v.to_dict() for v in views]}), 200


@bp.get("/<wallet_id>")
@require_auth
@document(summary="Consulter un portefeuille", tags=["wallets"], response_schema=_WALLET_SCHEMA)
def get_wallet(wallet_id: str) -> tuple[Response, int]:
    view = GetWallet(services=deps().services).execute(
        GetWalletCommand(user_id=str(current_principal().user_id), wallet_id=wallet_id)
    )
    return jsonify(view.to_dict()), 200


__all__ = ["bp"]
