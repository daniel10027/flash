"""Blueprints carte (BE-060) : ``cards_bp`` (titulaire) et ``card_webhook_bp`` (réseau)."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request
from pydantic import Field

from flash.application.card.authorizations import (
    AuthorizeCardPayment,
    AuthorizeCardPaymentCommand,
    CaptureCardPayment,
    CaptureCardPaymentCommand,
    RefundCardPayment,
    RefundCardPaymentCommand,
    ReverseCardAuthorization,
    ReverseCardAuthorizationCommand,
)
from flash.application.card.operations import (
    CloseCard,
    CloseCardCommand,
    FreezeCard,
    FreezeCardCommand,
    GetCard,
    GetCardCommand,
    GetCardSensitive,
    GetCardSensitiveCommand,
    IssueCard,
    IssueCardCommand,
    ListCards,
    ListCardsCommand,
    SetCardLimits,
    SetCardLimitsCommand,
    UnfreezeCard,
    UnfreezeCardCommand,
)
from flash.interface.container import deps
from flash.interface.http.schemas import ApiModel
from flash.interface.openapi import document
from flash.interface.security.auth import current_principal, require_auth
from flash.interface.security.card_webhook import require_card_webhook
from flash.interface.security.rate_limit import rate_limit

cards_bp = Blueprint("cards", __name__, url_prefix="/v1/cards")
card_webhook_bp = Blueprint("card_webhook", __name__, url_prefix="/v1/cards/authorizations")


def _json() -> dict[str, object]:
    return request.get_json(force=True, silent=True) or {}


_CARD_SCHEMA = {
    "type": "object",
    "properties": {
        "card_id": {"type": "string"},
        "network": {"type": "string", "enum": ["VISA", "MASTERCARD"]},
        "masked_pan": {"type": "string"},
        "last4": {"type": "string"},
        "expiry_month": {"type": "integer"},
        "expiry_year": {"type": "integer"},
        "status": {"type": "string", "enum": ["ACTIVE", "FROZEN", "CLOSED"]},
        "currency": {"type": "string"},
        "daily_limit_minor": {"type": "integer"},
        "monthly_limit_minor": {"type": "integer"},
        "channels": {"type": "array", "items": {"type": "string"}},
        "created_at": {"type": "string"},
    },
}


# ------------------------------------------------------------------ titulaire
@cards_bp.get("")
@require_auth
@document(summary="Lister mes cartes", tags=["cards"], response_schema=_CARD_SCHEMA)
def list_cards() -> tuple[Response, int]:
    views = ListCards(services=deps().services).execute(
        ListCardsCommand(user_id=str(current_principal().user_id))
    )
    return jsonify({"cards": [v.to_dict() for v in views]}), 200


class IssueCardRequest(ApiModel):
    network: str = Field(default="VISA", pattern="^(VISA|MASTERCARD)$")
    daily_limit_minor: int | None = Field(default=None, gt=0, examples=[500_000])
    monthly_limit_minor: int | None = Field(default=None, gt=0, examples=[5_000_000])
    channels: list[str] | None = Field(default=None, examples=[["ECOM", "CONTACTLESS"]])


@cards_bp.post("")
@require_auth
@rate_limit(name="card-issue", limit=5, per_seconds=3600, subject="user")
@document(
    summary="Émettre une carte virtuelle",
    tags=["cards"],
    status_code=201,
    request_schema=IssueCardRequest.model_json_schema(),
    response_schema=_CARD_SCHEMA,
)
def issue_card() -> tuple[Response, int]:
    body = IssueCardRequest.model_validate(_json())
    view = IssueCard(services=deps().services, issuer=deps().card_issuer).execute(
        IssueCardCommand(
            user_id=str(current_principal().user_id),
            network=body.network,
            daily_limit_minor=body.daily_limit_minor,
            monthly_limit_minor=body.monthly_limit_minor,
            channels=body.channels,
        )
    )
    return jsonify(view.to_dict()), 201


@cards_bp.get("/<card_id>")
@require_auth
@document(summary="Consulter une carte", tags=["cards"], response_schema=_CARD_SCHEMA)
def get_card(card_id: str) -> tuple[Response, int]:
    view = GetCard(services=deps().services).execute(
        GetCardCommand(user_id=str(current_principal().user_id), card_id=card_id)
    )
    return jsonify(view.to_dict()), 200


@cards_bp.post("/<card_id>/freeze")
@require_auth
@document(summary="Geler une carte", tags=["cards"], response_schema=_CARD_SCHEMA)
def freeze_card(card_id: str) -> tuple[Response, int]:
    view = FreezeCard(services=deps().services, issuer=deps().card_issuer).execute(
        FreezeCardCommand(user_id=str(current_principal().user_id), card_id=card_id)
    )
    return jsonify(view.to_dict()), 200


@cards_bp.post("/<card_id>/unfreeze")
@require_auth
@document(summary="Dégeler une carte", tags=["cards"], response_schema=_CARD_SCHEMA)
def unfreeze_card(card_id: str) -> tuple[Response, int]:
    view = UnfreezeCard(services=deps().services, issuer=deps().card_issuer).execute(
        UnfreezeCardCommand(user_id=str(current_principal().user_id), card_id=card_id)
    )
    return jsonify(view.to_dict()), 200


@cards_bp.post("/<card_id>/close")
@require_auth
@document(summary="Clôturer une carte (définitif)", tags=["cards"], response_schema=_CARD_SCHEMA)
def close_card(card_id: str) -> tuple[Response, int]:
    view = CloseCard(services=deps().services, issuer=deps().card_issuer).execute(
        CloseCardCommand(user_id=str(current_principal().user_id), card_id=card_id)
    )
    return jsonify(view.to_dict()), 200


class SetLimitsRequest(ApiModel):
    daily_limit_minor: int = Field(gt=0, examples=[300_000])
    monthly_limit_minor: int = Field(gt=0, examples=[3_000_000])


@cards_bp.patch("/<card_id>/limits")
@require_auth
@document(
    summary="Modifier les plafonds jour / mois",
    tags=["cards"],
    request_schema=SetLimitsRequest.model_json_schema(),
    response_schema=_CARD_SCHEMA,
)
def set_card_limits(card_id: str) -> tuple[Response, int]:
    body = SetLimitsRequest.model_validate(_json())
    view = SetCardLimits(services=deps().services).execute(
        SetCardLimitsCommand(
            user_id=str(current_principal().user_id),
            card_id=card_id,
            daily_limit_minor=body.daily_limit_minor,
            monthly_limit_minor=body.monthly_limit_minor,
        )
    )
    return jsonify(view.to_dict()), 200


@cards_bp.post("/<card_id>/reveal")
@require_auth
@rate_limit(name="card-reveal", limit=3, per_seconds=300, subject="user")
@document(
    summary="Révéler PAN / CVV (flux court, audité, jamais journalisé)",
    tags=["cards"],
)
def reveal_card(card_id: str) -> tuple[Response, int]:
    secret = GetCardSensitive(services=deps().services, issuer=deps().card_issuer).execute(
        GetCardSensitiveCommand(user_id=str(current_principal().user_id), card_id=card_id)
    )
    resp = jsonify(secret.to_dict())
    resp.headers["Cache-Control"] = "no-store"
    return resp, 200


# ------------------------------------------------------------------ webhook réseau
class AuthorizeRequest(ApiModel):
    authorization_id: str = Field(min_length=8, max_length=80)
    pan_token: str = Field(min_length=8, max_length=64)
    amount_minor: int = Field(gt=0)
    channel: str = Field(pattern="^(ECOM|CONTACTLESS|ATM)$")
    merchant_name: str | None = Field(default=None, max_length=140)


@card_webhook_bp.post("")
@require_card_webhook
@document(
    summary="Réseau : demande d'autorisation carte",
    tags=["cards"],
    secured=False,
    status_code=200,
    request_schema=AuthorizeRequest.model_json_schema(),
)
def authorize() -> tuple[Response, int]:
    body = AuthorizeRequest.model_validate(_json())
    decision = AuthorizeCardPayment(services=deps().services).execute(
        AuthorizeCardPaymentCommand(
            authorization_id=body.authorization_id,
            pan_token=body.pan_token,
            amount_minor=body.amount_minor,
            channel=body.channel,
            merchant_name=body.merchant_name,
        )
    )
    return jsonify(decision.to_dict()), 200


class CaptureRequest(ApiModel):
    amount_minor: int | None = Field(default=None, gt=0)


@card_webhook_bp.post("/<authorization_id>/capture")
@require_card_webhook
@document(summary="Réseau : capture d'une autorisation", tags=["cards"], secured=False)
def capture(authorization_id: str) -> tuple[Response, int]:
    body = CaptureRequest.model_validate(_json())
    result = CaptureCardPayment(services=deps().services).execute(
        CaptureCardPaymentCommand(authorization_id=authorization_id, amount_minor=body.amount_minor)
    )
    return jsonify(result.to_dict()), 200


@card_webhook_bp.post("/<authorization_id>/reverse")
@require_card_webhook
@document(
    summary="Réseau : annulation d'une autorisation non capturée",
    tags=["cards"],
    secured=False,
)
def reverse(authorization_id: str) -> tuple[Response, int]:
    result = ReverseCardAuthorization(services=deps().services).execute(
        ReverseCardAuthorizationCommand(authorization_id=authorization_id)
    )
    return jsonify(result.to_dict()), 200


@card_webhook_bp.post("/<authorization_id>/refund")
@require_card_webhook
@document(summary="Réseau : remboursement d'une capture", tags=["cards"], secured=False)
def refund(authorization_id: str) -> tuple[Response, int]:
    result = RefundCardPayment(services=deps().services).execute(
        RefundCardPaymentCommand(authorization_id=authorization_id)
    )
    return jsonify(result.to_dict()), 200


__all__ = ["card_webhook_bp", "cards_bp"]
