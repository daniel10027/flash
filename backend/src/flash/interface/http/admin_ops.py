"""Blueprint back-office : tâches d'exploitation (BE-044/045). Protégé par ``X-Admin-Key``."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify

from flash.application.jobs.card_reconcile import ReconcileCardSettlements
from flash.application.jobs.expire import ExpireStaleOperations
from flash.application.jobs.merchant_settle import SettleDueMerchants
from flash.application.jobs.reconcile import ReconcileWalletBalances
from flash.application.jobs.savings import AccrueSavingsInterest, RunScheduledSavings
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


@bp.post("/jobs/savings/contributions")
@require_admin
@document(
    summary="Back-office : prélever les versements d'épargne programmés échus",
    tags=["admin"],
    secured=False,
)
def run_scheduled_savings() -> tuple[Response, int]:
    report = RunScheduledSavings(services=deps().services).execute()
    return jsonify(report.to_dict()), 200


@bp.post("/jobs/savings/interest")
@require_admin
@document(
    summary="Back-office : accroître et capitaliser les intérêts d'épargne",
    tags=["admin"],
    secured=False,
)
def run_savings_interest() -> tuple[Response, int]:
    report = AccrueSavingsInterest(services=deps().services).execute()
    return jsonify(report.to_dict()), 200


@bp.post("/jobs/merchants/settle")
@require_admin
@document(
    summary="Back-office : régler les marchands dont l'échéance est atteinte",
    tags=["admin"],
    secured=False,
)
def run_merchant_settle() -> tuple[Response, int]:
    report = SettleDueMerchants(
        services=deps().services, bank=deps().bank_gateway
    ).execute()
    return jsonify(report.to_dict()), 200


@bp.post("/jobs/cards/reconcile")
@require_admin
@document(
    summary="Back-office : rapprocher les règlements carte avec le ledger",
    tags=["admin"],
    secured=False,
)
def run_card_reconcile() -> tuple[Response, int]:
    report = ReconcileCardSettlements(services=deps().services).execute()
    return jsonify(report.to_dict()), 200 if report.ok else 409


__all__ = ["bp"]
