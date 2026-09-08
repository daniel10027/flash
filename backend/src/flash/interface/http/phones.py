"""Blueprint ``phones`` — gestion des numéros du compte authentifié (BE-028)."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request
from pydantic import Field

from flash.application.identity.phone_numbers import (
    AddPhoneNumber,
    AddPhoneNumberCommand,
    ListPhoneNumbers,
    ListPhoneNumbersCommand,
    RemovePhoneNumber,
    RemovePhoneNumberCommand,
    SetPrimaryPhoneNumber,
    SetPrimaryPhoneNumberCommand,
    VerifyPhoneNumber,
    VerifyPhoneNumberCommand,
)
from flash.interface.container import deps
from flash.interface.http.schemas import ApiModel
from flash.interface.openapi import document
from flash.interface.security.auth import current_principal, require_auth
from flash.interface.security.rate_limit import rate_limit

bp = Blueprint("phones", __name__, url_prefix="/v1/phones")

_PHONE = Field(min_length=6, max_length=24, examples=["+2250700000000"])


class PhoneRef(ApiModel):
    phone_number: str = _PHONE
    country: str | None = Field(default=None, min_length=2, max_length=2)


class VerifyPhoneRequest(PhoneRef):
    code: str = Field(min_length=4, max_length=8)


def _uid() -> str:
    return str(current_principal().user_id)


def _body() -> dict[str, object]:
    return request.get_json(force=True, silent=True) or {}


@bp.get("")
@require_auth
@document(summary="Lister les numéros du compte", tags=["phones"])
def list_phones() -> tuple[Response, int]:
    views = ListPhoneNumbers(services=deps().services).execute(
        ListPhoneNumbersCommand(user_id=_uid())
    )
    return jsonify({"phone_numbers": [v.to_dict() for v in views]}), 200


@bp.post("")
@require_auth
@rate_limit(name="add-phone", limit=5, per_seconds=3600, subject="user")
@document(
    summary="Ajouter un numéro (envoie un code de vérification)",
    tags=["phones"],
    status_code=202,
    request_schema=PhoneRef.model_json_schema(),
)
def add_phone() -> tuple[Response, int]:
    body = PhoneRef.model_validate(_body())
    result = AddPhoneNumber(services=deps().services, otp=deps().otp).execute(
        AddPhoneNumberCommand(user_id=_uid(), phone_number=body.phone_number, country=body.country)
    )
    return jsonify(
        {"masked": result.masked, "verification_required": result.verification_required}
    ), 202


@bp.post("/verify")
@require_auth
@document(
    summary="Vérifier un numéro ajouté avec le code reçu",
    tags=["phones"],
    request_schema=VerifyPhoneRequest.model_json_schema(),
)
def verify_phone() -> tuple[Response, int]:
    body = VerifyPhoneRequest.model_validate(_body())
    view = VerifyPhoneNumber(services=deps().services, otp=deps().otp).execute(
        VerifyPhoneNumberCommand(
            user_id=_uid(),
            phone_number=body.phone_number,
            code=body.code,
            country=body.country,
        )
    )
    return jsonify(view.to_dict()), 200


@bp.delete("")
@require_auth
@document(
    summary="Retirer un numéro (ni le dernier, ni le principal)",
    tags=["phones"],
    status_code=204,
    request_schema=PhoneRef.model_json_schema(),
)
def remove_phone() -> tuple[Response, int]:
    body = PhoneRef.model_validate(_body())
    RemovePhoneNumber(services=deps().services).execute(
        RemovePhoneNumberCommand(
            user_id=_uid(), phone_number=body.phone_number, country=body.country
        )
    )
    return Response(status=204), 204


@bp.post("/primary")
@require_auth
@document(
    summary="Définir le numéro principal (doit être vérifié)",
    tags=["phones"],
    request_schema=PhoneRef.model_json_schema(),
)
def set_primary() -> tuple[Response, int]:
    body = PhoneRef.model_validate(_body())
    views = SetPrimaryPhoneNumber(services=deps().services).execute(
        SetPrimaryPhoneNumberCommand(
            user_id=_uid(), phone_number=body.phone_number, country=body.country
        )
    )
    return jsonify({"phone_numbers": [v.to_dict() for v in views]}), 200


__all__ = ["bp"]
