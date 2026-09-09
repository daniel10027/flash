"""Blueprint back-office : tâches d'exploitation (BE-044/045). Protégé par ``X-Admin-Key``."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify

from flash.application.jobs.expire import ExpireStaleOperations
from flash.application.jobs.reconcile import ReconcileWalletBalances
from flash.interface.container import deps
from flash.interface.openapi import document
from flash.interface.security.admin import require_admin

bp = Blueprint("admin_ops", __name__, url_prefix="/v1/admin")


@bp.post("/jobs/expire")
@require_admin
@document(
    summary="Back-office : expirer les opérations en attente périmées",
    tags=["admin"],
    secured=False,
)
def run_expire() -> tuple[Response, int]:
    report = ExpireStaleOperations(services=deps().services).execute()
    return jsonify(report.to_dict()), 200


@bp.post("/reconcile")
@require_admin
@document(
    summary="Back-office : réconcilier les soldes des portefeuilles avec le ledger",
    tags=["admin"],
    secured=False,
)
def run_reconcile() -> tuple[Response, int]:
    report = ReconcileWalletBalances(services=deps().services).execute()
    return jsonify(report.to_dict()), 200 if report.ok else 409


__all__ = ["bp"]
