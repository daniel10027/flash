"""Blueprint ``auth`` — inscription (BE-025) ; connexion et OTP viendront (BE-026/027)."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request
from pydantic import Field
from werkzeug.exceptions import BadRequest

from flash.application.identity.register_user import RegisterUser, RegisterUserCommand
from flash.interface.container import deps
from flash.interface.http.schemas import ApiModel
from flash.interface.openapi import document

bp = Blueprint("auth", __name__, url_prefix="/v1/auth")


class RegisterRequest(ApiModel):
    phone_number: str = Field(min_length=6, max_length=24, examples=["+2250700000000"])
    pin: str = Field(min_length=4, max_length=6, examples=["1397"])
    country: str = Field(min_length=2, max_length=2, examples=["CI"])


def _idempotency_key() -> str:
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key:
        raise BadRequest("En-tête Idempotency-Key requis pour cette opération.")
    return key


@bp.post("/register")
@document(
    summary="Créer un compte (en attente d'activation par OTP)",
    tags=["auth"],
    secured=False,
    idempotent=True,
    status_code=201,
    request_schema=RegisterRequest.model_json_schema(),
    response_schema={
        "type": "object",
        "properties": {
            "user_id": {"type": "string"},
            "wallet_id": {"type": "string"},
            "currency": {"type": "string"},
            "phone_number_masked": {"type": "string"},
            "activation_required": {"type": "boolean"},
        },
    },
)
def register() -> tuple[Response, int]:
    body = RegisterRequest.model_validate(request.get_json(force=True, silent=True) or {})
    use_case = RegisterUser(
        services=deps().services,
        countries=deps().countries,
        pins=deps().pins,
        otp=deps().otp,
    )
    result = use_case.execute(
        RegisterUserCommand(
            phone_number=body.phone_number,
            pin=body.pin,
            country=body.country,
            idempotency_key=_idempotency_key(),
        )
    )
    return jsonify(result.to_dict()), 201


__all__ = ["bp"]
