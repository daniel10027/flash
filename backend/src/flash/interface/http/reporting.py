"""Blueprint exports réglementaires & comptables (BE-077). Rôles ``finance`` / ``admin``.

Balance générale à une date (avec contrôle d'équilibre), journal des écritures sur une
période, export CSV d'un mois calendaire.
"""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request

from flash.application.reporting.ledger_reports import (
    ExportMonthlyLedger,
    ExportMonthlyLedgerCommand,
    GetLedgerJournal,
    GetLedgerJournalCommand,
    GetTrialBalance,
    GetTrialBalanceCommand,
)
from flash.interface.container import deps
from flash.interface.openapi import document
from flash.interface.security.roles import require_role

bp = Blueprint("reporting", __name__, url_prefix="/v1/admin/reports")

_FINANCE = require_role("finance", "admin")


@bp.get("/trial-balance")
@_FINANCE
@document(
    summary="Compta : balance générale du ledger à une date (contrôle d'équilibre)",
    tags=["admin"],
    secured=False,
)
def trial_balance() -> tuple[Response, int]:
    view = GetTrialBalance(services=deps().services).execute(
        GetTrialBalanceCommand(as_of=request.args.get("as_of", ""))
    )
    return jsonify(view.to_dict()), 200 if view.balanced else 409


@bp.get("/journal")
@_FINANCE
@document(
    summary="Compta : journal chronologique des écritures sur une période",
    tags=["admin"],
    secured=False,
)
def journal() -> tuple[Response, int]:
    entries = GetLedgerJournal(services=deps().services).execute(
        GetLedgerJournalCommand(
            start=request.args.get("start", ""),
            end=request.args.get("end", ""),
            limit=request.args.get("limit", default=1_000, type=int),
        )
    )
    return jsonify({"entries": [e.to_dict() for e in entries]}), 200


@bp.get("/monthly")
@_FINANCE
@document(
    summary="Compta : export CSV d'un mois du ledger (filtrable par devise/zone)",
    tags=["admin"],
    secured=False,
)
def monthly() -> Response:
    export = ExportMonthlyLedger(services=deps().services).execute(
        ExportMonthlyLedgerCommand(
            year=request.args.get("year", default=0, type=int),
            month=request.args.get("month", default=0, type=int),
            currency=request.args.get("currency"),
        )
    )
    resp = Response(export.content, mimetype=export.media_type)
    resp.headers["Content-Disposition"] = f'attachment; filename="{export.filename}"'
    return resp


__all__ = ["bp"]
