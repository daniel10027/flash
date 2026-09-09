"""Blueprint back-office agents (BE-072) : rattachement master ↔ sous-agent.

Rôles ``admin`` / ``finance``. Le versement périodique des commissions passe par
``POST /v1/admin/jobs/agents/commissions`` (blueprint ``admin_ops``).
"""

from __future__ import annotations

from flask import Blueprint, Response, jsonify, request
from pydantic import Field

from flash.application.agent.operations import (
    AttachAgentToMaster,
    AttachAgentToMasterCommand,
)
from flash.interface.container import deps
from flash.interface.http.schemas import ApiModel
from flash.interface.openapi import document
from flash.interface.security.roles import require_role

bp = Blueprint("admin_agents", __name__, url_prefix="/v1/admin/agents")


def _json() -> dict[str, object]:
    return request.get_json(force=True, silent=True) or {}


class AttachMasterRequest(ApiModel):
    master_agent_id: str = Field(min_length=8, max_length=64)


@bp.post("/<agent_id>/master")
@require_role("admin", "finance")
@document(
    summary="Back-office : rattacher un agent à un master (hiérarchie)",
    tags=["admin"],
    secured=False,
    request_schema=AttachMasterRequest.model_json_schema(),
)
def attach_master(agent_id: str) -> tuple[Response, int]:
    body = AttachMasterRequest.model_validate(_json())
    view = AttachAgentToMaster(services=deps().services).execute(
        AttachAgentToMasterCommand(
            agent_id=agent_id, master_agent_id=body.master_agent_id
        )
    )
    return jsonify(view.to_dict()), 200


__all__ = ["bp"]
