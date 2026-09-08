"""Blueprint ``auth`` : inscription, activation OTP, connexion, rafraîchissement,
déconnexion (BE-025 → BE-027)."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request
from pydantic import Field
from werkzeug.exceptions import BadRequest

from flash.application.auth.login import Login, LoginCommand
from flash.application.auth.verify_otp import (
    ResendOtp,
    ResendOtpCommand,
    VerifyOtp,
    VerifyOtpCommand,
)
from flash.application.identity.register_user import RegisterUser, RegisterUserCommand
from flash.interface.container import deps
from flash.interface.http.schemas import ApiModel
from flash.interface.openapi import document
from flash.interface.security.auth import current_principal, require_auth
from flash.interface.security.rate_limit import rate_limit
from flash.interface.security.wiring import security

bp = Blueprint("auth", __name__, url_prefix="/v1/auth")

_PHONE = Field(min_length=6, max_length=24, examples=["+2250700000000"])
_COUNTRY = Field(min_length=2, max_length=2, examples=["CI"])
_PIN = Field(min_length=4, max_length=6, examples=["1397"])
_DEVICE = Field(min_length=1, max_length=128, examples=["a1b2c3d4"])


class RegisterRequest(ApiModel):
    phone_number: str = _PHONE
    pin: str = _PIN
    country: str = _COUNTRY


class VerifyOtpRequest(ApiModel):
    phone_number: str = _PHONE
    country: str = _COUNTRY
    code: str = Field(min_length=4, max_length=8, examples=["000000"])
    device_id: str = _DEVICE


class ResendOtpRequest(ApiModel):
    phone_number: str = _PHONE
    country: str = _COUNTRY


class LoginRequest(ApiModel):
    phone_number: str = _PHONE
    country: str = _COUNTRY
    pin: str = _PIN
    device_id: str = _DEVICE


class RefreshRequest(ApiModel):
    refresh_token: str = Field(min_length=10)


_TOKENS_SCHEMA = {
    "type": "object",
    "properties": {
        "access_token": {"type": "string"},
        "refresh_token": {"type": "string"},
        "access_expires_in": {"type": "integer"},
        "refresh_expires_in": {"type": "integer"},
        "user_id": {"type": "string"},
    },
}


def _idempotency_key() -> str:
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key:
        raise BadRequest("En-tête Idempotency-Key requis pour cette opération.")
    return key


def _json() -> dict[str, object]:
    return request.get_json(force=True, silent=True) or {}


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
    body = RegisterRequest.model_validate(_json())
    result = RegisterUser(
        services=deps().services,
        countries=deps().countries,
        pins=deps().pins,
        otp=deps().otp,
    ).execute(
        RegisterUserCommand(
            phone_number=body.phone_number,
            pin=body.pin,
            country=body.country,
            idempotency_key=_idempotency_key(),
        )
    )
    return jsonify(result.to_dict()), 201


@bp.post("/verify-otp")
@document(
    summary="Activer un compte avec le code reçu par SMS",
    tags=["auth"],
    secured=False,
    status_code=200,
    request_schema=VerifyOtpRequest.model_json_schema(),
    response_schema=_TOKENS_SCHEMA,
)
def verify_otp() -> tuple[Response, int]:
    body = VerifyOtpRequest.model_validate(_json())
    tokens = VerifyOtp(
        services=deps().services,
        countries=deps().countries,
        otp=deps().otp,
        tokens=deps().tokens,
    ).execute(
        VerifyOtpCommand(
            phone_number=body.phone_number,
            country=body.country,
            code=body.code,
            device_id=body.device_id,
        )
    )
    return jsonify(tokens.to_dict()), 200


@bp.post("/resend-otp")
@rate_limit(name="resend-otp", limit=3, per_seconds=600, subject="ip+route")
@document(
    summary="Renvoyer le code d'activation",
    tags=["auth"],
    secured=False,
    status_code=200,
    request_schema=ResendOtpRequest.model_json_schema(),
)
def resend_otp() -> tuple[Response, int]:
    body = ResendOtpRequest.model_validate(_json())
    result = ResendOtp(
        services=deps().services, countries=deps().countries, otp=deps().otp
    ).execute(ResendOtpCommand(phone_number=body.phone_number, country=body.country))
    return jsonify(
        {"phone_number_masked": result.phone_number_masked, "resent": result.resent}
    ), 200


@bp.post("/login")
@rate_limit(name="login", limit=10, per_seconds=300, subject="ip+route")
@document(
    summary="Se connecter avec numéro + code secret",
    tags=["auth"],
    secured=False,
    status_code=200,
    request_schema=LoginRequest.model_json_schema(),
    response_schema=_TOKENS_SCHEMA,
)
def login() -> tuple[Response, int]:
    body = LoginRequest.model_validate(_json())
    tokens = Login(services=deps().services, pins=deps().pins, tokens=deps().tokens).execute(
        LoginCommand(
            phone_number=body.phone_number,
            country=body.country,
            pin=body.pin,
            device_id=body.device_id,
        )
    )
    return jsonify(tokens.to_dict()), 200


@bp.post("/refresh")
@document(
    summary="Échanger un refresh token contre une nouvelle paire",
    tags=["auth"],
    secured=False,
    status_code=200,
    request_schema=RefreshRequest.model_json_schema(),
    response_schema=_TOKENS_SCHEMA,
)
def refresh() -> tuple[Response, int]:
    body = RefreshRequest.model_validate(_json())
    pair = security().tokens.rotate(body.refresh_token)
    return jsonify(
        {
            "access_token": pair.access_token,
            "refresh_token": pair.refresh_token,
            "access_expires_in": pair.access_expires_in,
            "refresh_expires_in": pair.refresh_expires_in,
        }
    ), 200


@bp.post("/logout")
@require_auth
@document(summary="Révoquer la session de l'appareil courant", tags=["auth"], status_code=204)
def logout() -> tuple[Response, int]:
    security().tokens.logout(current_principal())
    return Response(status=204), 204


__all__ = ["bp"]
