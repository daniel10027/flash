"""Blueprint conformité / AML (BE-076). Rôles ``compliance`` / ``admin``.

Alertes AML (file, revue avec gel préventif à l'escalade, ouverture manuelle), export
STR/CTR au format CSV, et le job de scan.
"""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request
from pydantic import Field

from flash.application.compliance.detection import ScanForAmlAlerts
from flash.application.compliance.operations import (
    ExportSuspiciousActivity,
    ExportSuspiciousActivityCommand,
    ListComplianceAlerts,
    ListComplianceAlertsCommand,
    RaiseManualAlert,
    RaiseManualAlertCommand,
    ReviewComplianceAlert,
    ReviewComplianceAlertCommand,
)
from flash.interface.container import deps
from flash.interface.http.schemas import ApiModel
from flash.interface.openapi import document
from flash.interface.security.roles import current_actor, require_role

bp = Blueprint("compliance", __name__, url_prefix="/v1/admin/compliance")
jobs_bp = Blueprint("compliance_jobs", __name__, url_prefix="/v1/admin/jobs")

_ANALYST = require_role("compliance", "admin")


def _json() -> dict[str, object]:
    return request.get_json(force=True, silent=True) or {}


def _role() -> str:
    actor = current_actor()
    return actor.split(":", 1)[1] if ":" in actor else actor


@bp.get("/alerts")
@_ANALYST
@document(
    summary="Conformité : file d'alertes AML (ouvertes, ou filtrées par statut)",
    tags=["admin"],
    secured=False,
)
def list_alerts() -> tuple[Response, int]:
    views = ListComplianceAlerts(services=deps().services).execute(
        ListComplianceAlertsCommand(status=request.args.get("status"))
    )
    return jsonify({"alerts": [v.to_dict() for v in views]}), 200


class ManualAlertRequest(ApiModel):
    user_id: str = Field(min_length=8, max_length=64)
    reason: str = Field(min_length=1, max_length=500)


@bp.post("/alerts")
@_ANALYST
@document(
    summary="Conformité : ouvrir une alerte AML manuelle",
    tags=["admin"],
    secured=False,
    status_code=201,
    request_schema=ManualAlertRequest.model_json_schema(),
)
def raise_manual_alert() -> tuple[Response, int]:
    body = ManualAlertRequest.model_validate(_json())
    view = RaiseManualAlert(
        services=deps().services, audit=deps().audit, clock=deps().services.clock
    ).execute(
        RaiseManualAlertCommand(
            user_id=body.user_id,
            reason=body.reason,
            analyst=current_actor(),
            role=_role(),
        )
    )
    return jsonify(view.to_dict()), 201


class ReviewAlertRequest(ApiModel):
    decision: str = Field(examples=["clear", "escalate"])
    note: str = Field(default="", max_length=500)


@bp.post("/alerts/<alert_id>/review")
@_ANALYST
@document(
    summary="Conformité : clôturer (faux positif) ou escalader (STR + gel du compte)",
    tags=["admin"],
    secured=False,
    request_schema=ReviewAlertRequest.model_json_schema(),
)
def review_alert(alert_id: str) -> tuple[Response, int]:
    body = ReviewAlertRequest.model_validate(_json())
    view = ReviewComplianceAlert(
        services=deps().services, audit=deps().audit, clock=deps().services.clock
    ).execute(
        ReviewComplianceAlertCommand(
            alert_id=alert_id,
            decision=body.decision,
            note=body.note,
            analyst=current_actor(),
            role=_role(),
        )
    )
    return jsonify(view.to_dict()), 200


@bp.get("/reports/str")
@_ANALYST
@document(
    summary="Conformité : export CSV des alertes AML sur une période (STR/CTR)",
    tags=["admin"],
    secured=False,
)
def export_str() -> Response:
    export = ExportSuspiciousActivity(services=deps().services).execute(
        ExportSuspiciousActivityCommand(
            start=request.args.get("start", ""),
            end=request.args.get("end", ""),
        )
    )
    resp = Response(export.content, mimetype=export.media_type)
    resp.headers["Content-Disposition"] = f'attachment; filename="{export.filename}"'
    return resp


@jobs_bp.post("/compliance/scan")
@require_role("compliance", "admin")
@document(
    summary="Back-office : lancer le scan AML (seuil / structuration / vélocité)",
    tags=["admin"],
    secured=False,
)
def run_aml_scan() -> tuple[Response, int]:
    report = ScanForAmlAlerts(
        services=deps().services, thresholds=deps().aml_thresholds
    ).execute()
    return jsonify(report.to_dict()), 200


__all__ = ["bp", "jobs_bp"]
