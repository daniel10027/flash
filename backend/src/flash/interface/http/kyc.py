"""Blueprint ``kyc`` — vérification d'identité par paliers (BE-029).

Client : soumettre un dossier, suivre son statut, le retirer. Back-office (``X-Admin-Key``)
: approuver ou rejeter un dossier.
"""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request
from pydantic import Field
from werkzeug.exceptions import BadRequest

from flash.application.identity.kyc import (
    GetKycStatus,
    GetKycStatusCommand,
    KycDocumentInput,
    ListMyKycCases,
    ListMyKycCasesCommand,
    ReviewKyc,
    ReviewKycCommand,
    SubmitKyc,
    SubmitKycCommand,
    WithdrawKyc,
    WithdrawKycCommand,
)
from flash.interface.container import deps
from flash.interface.http.schemas import ApiModel
from flash.interface.openapi import document
from flash.interface.security.admin import require_admin
from flash.interface.security.auth import current_principal, require_auth
from flash.interface.security.rate_limit import rate_limit

bp = Blueprint("kyc", __name__, url_prefix="/v1/kyc")
admin_bp = Blueprint("kyc_admin", __name__, url_prefix="/v1/admin/kyc")


def _idem_key() -> str:
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key:
        raise BadRequest("En-tête Idempotency-Key requis pour cette opération.")
    return key


def _json() -> dict[str, object]:
    return request.get_json(force=True, silent=True) or {}


class KycDocumentPayload(ApiModel):
    kind: str = Field(examples=["ID_FRONT", "SELFIE"])
    content_base64: str = Field(min_length=8)
    content_type: str = Field(examples=["image/jpeg"])


class SubmitKycRequest(ApiModel):
    target_tier: int = Field(ge=1, le=2, examples=[1])
    documents: list[KycDocumentPayload] = Field(min_length=1, max_length=6)


class ReviewKycRequest(ApiModel):
    approve: bool
    reason: str = Field(default="", max_length=500)


@bp.get("/status")
@require_auth
@document(summary="Palier KYC courant et dossier en attente éventuel", tags=["kyc"])
def kyc_status() -> tuple[Response, int]:
    view = GetKycStatus(services=deps().services).execute(
        GetKycStatusCommand(user_id=str(current_principal().user_id))
    )
    return jsonify(view.to_dict()), 200


@bp.get("/submissions")
@require_auth
@document(summary="Historique des dossiers KYC de l'utilisateur", tags=["kyc"])
def list_submissions() -> tuple[Response, int]:
    cases = ListMyKycCases(services=deps().services).execute(
        ListMyKycCasesCommand(user_id=str(current_principal().user_id))
    )
    return jsonify({"submissions": [c.to_dict() for c in cases]}), 200


@bp.post("/submissions")
@require_auth
@rate_limit(name="kyc-submit", limit=5, per_seconds=3600, subject="user")
@document(
    summary="Soumettre un dossier de vérification d'identité",
    tags=["kyc"],
    idempotent=True,
    status_code=201,
    request_schema=SubmitKycRequest.model_json_schema(),
)
def submit_kyc() -> tuple[Response, int]:
    body = SubmitKycRequest.model_validate(_json())
    view = SubmitKyc(services=deps().services, documents=deps().documents).execute(
        SubmitKycCommand(
            user_id=str(current_principal().user_id),
            target_tier=body.target_tier,
            documents=[
                KycDocumentInput(
                    kind=d.kind, content_base64=d.content_base64, content_type=d.content_type
                )
                for d in body.documents
            ],
            idempotency_key=_idem_key(),
        )
    )
    return jsonify(view.to_dict()), 201


@bp.post("/submissions/<case_id>/withdraw")
@require_auth
@document(summary="Retirer un dossier KYC en attente", tags=["kyc"], status_code=204)
def withdraw_kyc(case_id: str) -> tuple[Response, int]:
    WithdrawKyc(services=deps().services).execute(
        WithdrawKycCommand(user_id=str(current_principal().user_id), case_id=case_id)
    )
    return Response(status=204), 204


@admin_bp.post("/submissions/<case_id>/review")
@require_admin
@document(
    summary="Back-office : approuver ou rejeter un dossier KYC",
    tags=["kyc", "admin"],
    secured=False,
    request_schema=ReviewKycRequest.model_json_schema(),
)
def review_kyc(case_id: str) -> tuple[Response, int]:
    body = ReviewKycRequest.model_validate(_json())
    reviewer_id = request.headers.get("X-Admin-Reviewer", "00000000-0000-0000-0000-000000000000")
    view = ReviewKyc(services=deps().services).execute(
        ReviewKycCommand(
            case_id=case_id,
            reviewer_id=reviewer_id,
            approve=body.approve,
            reason=body.reason,
        )
    )
    return jsonify(view.to_dict()), 200


__all__ = ["admin_bp", "bp"]
