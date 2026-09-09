"""Job BE-073 : verser les commissions agent dues au-dessus d'un seuil.

Pour chaque agent dont ``commission_owed`` ≥ ``threshold_minor`` (et dont le float couvre
le montant), déplace le dû du float vers le portefeuille de l'agent
(``AGENT_FLOAT`` → ``CLIENT_LIABILITY``). Idempotent : relancé, plus rien n'est dû.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flash.application.agent.operations import PayAgentCommission, PayAgentCommissionCommand
from flash.application.services import AppServices
from flash.domain.shared.errors import AgentFloatTooLow, InvalidInput

_DEFAULT_THRESHOLD_MINOR = 1_000


@dataclass(frozen=True, slots=True)
class AgentCommissionReport:
    checked: int
    paid: int
    paid_minor: int
    skipped: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked": self.checked,
            "paid": self.paid,
            "paid_minor": self.paid_minor,
            "skipped": self.skipped,
        }


class PayDueAgentCommissions:
    def __init__(
        self, *, services: AppServices, threshold_minor: int = _DEFAULT_THRESHOLD_MINOR
    ) -> None:
        self._services = services
        self._threshold = threshold_minor
        self._pay = PayAgentCommission(services=services)

    def execute(self) -> AgentCommissionReport:
        with self._services.uow() as uow:
            candidates = [
                a.user_id
                for a in uow.agents.list_with_commission_owed(self._threshold)
            ]

        checked = paid = paid_minor = skipped = 0
        for user_id in candidates:
            checked += 1
            try:
                before = self._owed(user_id)
                self._pay.execute(PayAgentCommissionCommand(agent_user_id=str(user_id)))
                paid += 1
                paid_minor += before
            except (AgentFloatTooLow, InvalidInput):
                skipped += 1
        return AgentCommissionReport(
            checked=checked, paid=paid, paid_minor=paid_minor, skipped=skipped
        )

    def _owed(self, user_id: object) -> int:
        with self._services.uow() as uow:
            agent = uow.agents.get_by_user_id(user_id)  # type: ignore[arg-type]
            return agent.commission_owed.amount_minor if agent else 0


__all__ = ["AgentCommissionReport", "PayDueAgentCommissions"]
