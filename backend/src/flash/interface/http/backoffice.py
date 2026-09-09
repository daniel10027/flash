"""Blueprint back-office comptes & support (BE-075).

RBAC : lectures ouvertes aux rôles ``support`` / ``compliance`` / ``finance`` / ``admin`` ;
gel/dégel réservé à ``support`` + ; contre-passation forcée à ``finance`` / ``admin``.
Chaque action est tracée dans le registre d'audit chaîné (voir ``application`` /
``GET /v1/admin/audit``).
"""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request
from pydantic import Field

from flash.application.backoffice.operations import (
    AddAccountNote,
    AddAccountNoteCommand,
    ForceTransferReversal,
    ForceTransferReversalCommand,
    GetAccountDetail,
    GetAccountDetailCommand,
    ListAccountNotes,
    ListAccountNotesCommand,
    ListAccountTransactions,
    ListAccountTransactionsCommand,
    ListSupportTickets,
    ListSupportTicketsCommand,
    OpenSupportTicket,
    OpenSupportTicketCommand,
    SearchAccount,
    SearchAccountCommand,
    SetAccountFrozen,
    SetAccountFrozenCommand,
    SetTicketStatus,
    SetTicketStatusCommand,
)
from flash.interface.container import deps
from flash.interface.http.schemas import ApiModel
from flash.interface.openapi import document
from flash.interface.security.roles import current_actor, require_role

bp = Blueprint("backoffice", __name__, url_prefix="/v1/admin")

_READ = require_role("support", "compliance", "finance", "admin")
_SUPPORT = require_role("support", "compliance", "finance", "admin")
_FINANCE = require_role("finance", "admin")


def _json() -> dict[str, object]:
    return request.get_json(force=True, silent=True) or {}


def _role() -> str:
    actor = current_actor()
    return actor.split(":", 1)[1] if ":" in actor else actor


# ------------------------------------------------------------------ comptes
@bp.get("/accounts")
@_READ
@document(
    summary="Back-office : rechercher un compte (id ou msisdn)",
    tags=["admin"],
    secured=False,
)
def search_account() -> tuple[Response, int]:
    query = request.args.get("q", "").strip()
    view = SearchAccount(services=deps().services).execute(SearchAccountCommand(query=query))
    return jsonify(view.to_dict()), 200


@bp.get("/accounts/<user_id>")
@_READ
@document(
    summary="Back-office : détail d'un compte (wallets, notes, tickets)",
    tags=["admin"],
    secured=False,
)
def account_detail(user_id: str) -> tuple[Response, int]:
    view = GetAccountDetail(services=deps().services).execute(
        GetAccountDetailCommand(user_id=user_id)
    )
    return jsonify(view.to_dict()), 200


@bp.get("/accounts/<user_id>/transactions")
@_READ
@document(summary="Back-office : transactions ledger d'un compte", tags=["admin"], secured=False)
def account_transactions(user_id: str) -> tuple[Response, int]:
    limit = request.args.get("limit", default=50, type=int)
    lines = ListAccountTransactions(services=deps().services).execute(
        ListAccountTransactionsCommand(user_id=user_id, limit=limit)
    )
    return jsonify({"transactions": [line.to_dict() for line in lines]}), 200


class FreezeRequest(ApiModel):
    frozen: bool
    reason: str = Field(default="", max_length=200)


@bp.post("/accounts/<user_id>/freeze")
@_SUPPORT
@document(
    summary="Back-office : geler / dégeler un compte",
    tags=["admin"],
    secured=False,
    request_schema=FreezeRequest.model_json_schema(),
)
def set_account_frozen(user_id: str) -> tuple[Response, int]:
    body = FreezeRequest.model_validate(_json())
    view = SetAccountFrozen(
        services=deps().services, audit=deps().audit, clock=deps().services.clock
    ).execute(
        SetAccountFrozenCommand(
            user_id=user_id,
            frozen=body.frozen,
            reason=body.reason,
            actor=current_actor(),
            role=_role(),
        )
    )
    return jsonify(view.to_dict()), 200


class ForceReversalRequest(ApiModel):
    transaction_id: str = Field(min_length=8, max_length=64)
    reason: str = Field(min_length=1, max_length=200)


@bp.post("/transactions/force-reversal")
@_FINANCE
@document(
    summary="Back-office : contre-passer de force un virement P2P",
    tags=["admin"],
    secured=False,
    request_schema=ForceReversalRequest.model_json_schema(),
)
def force_transfer_reversal() -> tuple[Response, int]:
    body = ForceReversalRequest.model_validate(_json())
    receipt = ForceTransferReversal(
        services=deps().services, audit=deps().audit, clock=deps().services.clock
    ).execute(
        ForceTransferReversalCommand(
            transaction_id=body.transaction_id,
            reason=body.reason,
            actor=current_actor(),
            role=_role(),
        )
    )
    return jsonify(receipt.to_dict()), 200


# ------------------------------------------------------------------ notes
class NoteRequest(ApiModel):
    body: str = Field(min_length=1, max_length=2000)


@bp.post("/accounts/<user_id>/notes")
@_SUPPORT
@document(
    summary="Back-office : ajouter une note sur un compte",
    tags=["admin"],
    secured=False,
    status_code=201,
    request_schema=NoteRequest.model_json_schema(),
)
def add_account_note(user_id: str) -> tuple[Response, int]:
    body = NoteRequest.model_validate(_json())
    view = AddAccountNote(
        services=deps().services, audit=deps().audit, clock=deps().services.clock
    ).execute(
        AddAccountNoteCommand(
            user_id=user_id, body=body.body, author=current_actor(), role=_role()
        )
    )
    return jsonify(view.to_dict()), 201


@bp.get("/accounts/<user_id>/notes")
@_READ
@document(summary="Back-office : notes d'un compte", tags=["admin"], secured=False)
def list_account_notes(user_id: str) -> tuple[Response, int]:
    views = ListAccountNotes(services=deps().services).execute(
        ListAccountNotesCommand(user_id=user_id)
    )
    return jsonify({"notes": [v.to_dict() for v in views]}), 200


# ------------------------------------------------------------------ tickets
class OpenTicketRequest(ApiModel):
    user_id: str = Field(min_length=8, max_length=64)
    subject: str = Field(min_length=1, max_length=160)


@bp.post("/tickets")
@_SUPPORT
@document(
    summary="Back-office : ouvrir un ticket de support",
    tags=["admin"],
    secured=False,
    status_code=201,
    request_schema=OpenTicketRequest.model_json_schema(),
)
def open_ticket() -> tuple[Response, int]:
    body = OpenTicketRequest.model_validate(_json())
    view = OpenSupportTicket(
        services=deps().services, audit=deps().audit, clock=deps().services.clock
    ).execute(
        OpenSupportTicketCommand(
            user_id=body.user_id,
            subject=body.subject,
            actor=current_actor(),
            role=_role(),
        )
    )
    return jsonify(view.to_dict()), 201


@bp.get("/tickets")
@_READ
@document(summary="Back-office : lister les tickets (filtre statut)", tags=["admin"], secured=False)
def list_tickets() -> tuple[Response, int]:
    views = ListSupportTickets(services=deps().services).execute(
        ListSupportTicketsCommand(status=request.args.get("status"))
    )
    return jsonify({"tickets": [v.to_dict() for v in views]}), 200


class TicketStatusRequest(ApiModel):
    status: str = Field(examples=["PENDING", "RESOLVED", "CLOSED", "OPEN"])


@bp.post("/tickets/<ticket_id>/status")
@_SUPPORT
@document(
    summary="Back-office : changer le statut d'un ticket",
    tags=["admin"],
    secured=False,
    request_schema=TicketStatusRequest.model_json_schema(),
)
def set_ticket_status(ticket_id: str) -> tuple[Response, int]:
    body = TicketStatusRequest.model_validate(_json())
    view = SetTicketStatus(
        services=deps().services, audit=deps().audit, clock=deps().services.clock
    ).execute(
        SetTicketStatusCommand(
            ticket_id=ticket_id,
            status=body.status,
            actor=current_actor(),
            role=_role(),
        )
    )
    return jsonify(view.to_dict()), 200


__all__ = ["bp"]
