"""Blueprints ``withdrawals`` (client) et ``agent`` (opérateur cash) — BE-034 → BE-036."""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request
from pydantic import Field
from werkzeug.exceptions import BadRequest

from flash.application.agent.operations import (
    AgentFloatCommand,
    GetAgentOverview,
    GetAgentOverviewCommand,
    ListAgentOperations,
    ListAgentOperationsCommand,
    LookupCustomer,
    LookupCustomerCommand,
    PayAgentCommission,
    PayAgentCommissionCommand,
    TopUpAgentFloat,
    WithdrawAgentFloat,
)
from flash.application.cash.operations import (
    CancelCashWithdrawal,
    CancelWithdrawalCommand,
    ConfirmCashWithdrawal,
    ConfirmWithdrawalCommand,
    CreateCashDeposit,
    CreateCashDepositCommand,
    InitiateCashWithdrawal,
    InitiateWithdrawalCommand,
)
from flash.interface.container import deps
from flash.interface.http.schemas import ApiModel
from flash.interface.openapi import document
from flash.interface.security.auth import current_principal, require_auth
from flash.interface.security.rate_limit import rate_limit

withdrawals_bp = Blueprint("withdrawals", __name__, url_prefix="/v1/withdrawals")
agent_bp = Blueprint("agent", __name__, url_prefix="/v1/agent")


def _idem_key() -> str:
    key = request.headers.get("Idempotency-Key", "").strip()
    if not key:
        raise BadRequest("En-tête Idempotency-Key requis pour cette opération.")
    return key


def _json() -> dict[str, object]:
    return request.get_json(force=True, silent=True) or {}


# ---------------------------------------------------------------- client : retrait
class InitiateWithdrawalRequest(ApiModel):
    amount_minor: int = Field(gt=0, examples=[20_000])


@withdrawals_bp.post("")
@require_auth
@rate_limit(name="withdrawal-init", limit=10, per_seconds=600, subject="user")
@document(
    summary="Générer un code de retrait cash (réserve les fonds)",
    tags=["cash"],
    idempotent=True,
    status_code=201,
    request_schema=InitiateWithdrawalRequest.model_json_schema(),
)
def initiate_withdrawal() -> tuple[Response, int]:
    body = InitiateWithdrawalRequest.model_validate(_json())
    ticket = InitiateCashWithdrawal(
        services=deps().services,
        pricing=deps().pricing,
        limits=deps().limits,
        kyc=deps().kyc,
        codes=deps().codes,
    ).execute(
        InitiateWithdrawalCommand(
            client_user_id=str(current_principal().user_id),
            amount_minor=body.amount_minor,
            idempotency_key=_idem_key(),
        )
    )
    return jsonify(ticket.to_dict()), 201


@withdrawals_bp.post("/<order_id>/cancel")
@require_auth
@document(
    summary="Annuler un retrait en attente (rend les fonds réservés)",
    tags=["cash"],
    status_code=204,
)
def cancel_withdrawal(order_id: str) -> tuple[Response, int]:
    CancelCashWithdrawal(services=deps().services).execute(
        CancelWithdrawalCommand(client_user_id=str(current_principal().user_id), order_id=order_id)
    )
    return Response(status=204), 204


# ------------------------------------------------------------------ agent
class AgentDepositRequest(ApiModel):
    client_phone_number: str = Field(min_length=6, max_length=24)
    amount_minor: int = Field(gt=0, examples=[50_000])
    country: str | None = Field(default=None, min_length=2, max_length=2)


class ConfirmWithdrawalRequest(ApiModel):
    code: str = Field(min_length=4, max_length=16)


@agent_bp.post("/deposits")
@require_auth
@rate_limit(name="agent-deposit", limit=60, per_seconds=60, subject="user")
@document(
    summary="Dépôt cash : l'agent crédite le portefeuille d'un client",
    tags=["cash"],
    idempotent=True,
    status_code=201,
    request_schema=AgentDepositRequest.model_json_schema(),
)
def agent_deposit() -> tuple[Response, int]:
    body = AgentDepositRequest.model_validate(_json())
    receipt = CreateCashDeposit(
        services=deps().services, limits=deps().limits, kyc=deps().kyc
    ).execute(
        CreateCashDepositCommand(
            agent_user_id=str(current_principal().user_id),
            client_phone_number=body.client_phone_number,
            amount_minor=body.amount_minor,
            idempotency_key=_idem_key(),
            country=body.country,
        )
    )
    return jsonify(receipt.to_dict()), 201


@agent_bp.post("/withdrawals/confirm")
@require_auth
@rate_limit(name="agent-withdrawal", limit=60, per_seconds=60, subject="user")
@document(
    summary="Retrait cash : l'agent confirme avec le code du client",
    tags=["cash"],
    status_code=200,
    request_schema=ConfirmWithdrawalRequest.model_json_schema(),
)
def agent_confirm_withdrawal() -> tuple[Response, int]:
    body = ConfirmWithdrawalRequest.model_validate(_json())
    result = ConfirmCashWithdrawal(services=deps().services, codes=deps().codes).execute(
        ConfirmWithdrawalCommand(agent_user_id=str(current_principal().user_id), code=body.code)
    )
    return jsonify(result.to_dict()), 200


# ------------------------------------------------------------ espace agent (BE-074)
@agent_bp.get("")
@require_auth
@document(summary="Tableau de bord agent : float, plafond, commissions", tags=["agent"])
def agent_overview() -> tuple[Response, int]:
    view = GetAgentOverview(services=deps().services).execute(
        GetAgentOverviewCommand(agent_user_id=str(current_principal().user_id))
    )
    return jsonify(view.to_dict()), 200


@agent_bp.get("/operations")
@require_auth
@document(summary="Historique des opérations cash traitées par l'agent", tags=["agent"])
def agent_operations() -> tuple[Response, int]:
    limit = request.args.get("limit", default=50, type=int)
    lines = ListAgentOperations(services=deps().services).execute(
        ListAgentOperationsCommand(
            agent_user_id=str(current_principal().user_id), limit=limit
        )
    )
    return jsonify({"operations": [line.to_dict() for line in lines]}), 200


class AgentFloatRequest(ApiModel):
    amount_minor: int = Field(gt=0, examples=[500_000])


@agent_bp.post("/float/topup")
@require_auth
@rate_limit(name="agent-float", limit=30, per_seconds=60, subject="user")
@document(
    summary="Approvisionner le float de l'agent (achat d'e-money)",
    tags=["agent"],
    idempotent=True,
    status_code=201,
    request_schema=AgentFloatRequest.model_json_schema(),
)
def agent_float_topup() -> tuple[Response, int]:
    body = AgentFloatRequest.model_validate(_json())
    receipt = TopUpAgentFloat(services=deps().services).execute(
        AgentFloatCommand(
            agent_user_id=str(current_principal().user_id),
            amount_minor=body.amount_minor,
            idempotency_key=_idem_key(),
        )
    )
    return jsonify(receipt.to_dict()), 201


@agent_bp.post("/float/withdraw")
@require_auth
@rate_limit(name="agent-float", limit=30, per_seconds=60, subject="user")
@document(
    summary="Restituer du float de l'agent (remboursé en banque)",
    tags=["agent"],
    idempotent=True,
    status_code=201,
    request_schema=AgentFloatRequest.model_json_schema(),
)
def agent_float_withdraw() -> tuple[Response, int]:
    body = AgentFloatRequest.model_validate(_json())
    receipt = WithdrawAgentFloat(services=deps().services).execute(
        AgentFloatCommand(
            agent_user_id=str(current_principal().user_id),
            amount_minor=body.amount_minor,
            idempotency_key=_idem_key(),
        )
    )
    return jsonify(receipt.to_dict()), 201


class CommissionPayoutRequest(ApiModel):
    amount_minor: int | None = Field(default=None, gt=0)


@agent_bp.post("/commission/payout")
@require_auth
@rate_limit(name="agent-commission", limit=20, per_seconds=60, subject="user")
@document(
    summary="Verser la commission due sur le portefeuille de l'agent",
    tags=["agent"],
    status_code=200,
    request_schema=CommissionPayoutRequest.model_json_schema(),
)
def agent_commission_payout() -> tuple[Response, int]:
    body = CommissionPayoutRequest.model_validate(_json())
    view = PayAgentCommission(services=deps().services).execute(
        PayAgentCommissionCommand(
            agent_user_id=str(current_principal().user_id), amount_minor=body.amount_minor
        )
    )
    return jsonify(view.to_dict()), 200


@agent_bp.get("/customers")
@require_auth
@document(
    summary="Recherche d'un client par numéro (données minimales pour l'agence)",
    tags=["agent"],
)
def agent_customer_lookup() -> tuple[Response, int]:
    phone = request.args.get("msisdn", "").strip()
    if not phone:
        raise BadRequest("Paramètre `msisdn` requis.")
    view = LookupCustomer(services=deps().services).execute(
        LookupCustomerCommand(
            agent_user_id=str(current_principal().user_id),
            phone_number=phone,
            country=request.args.get("country"),
        )
    )
    return jsonify(view.to_dict()), 200


__all__ = ["agent_bp", "withdrawals_bp"]
