"""Port du sous-domaine agent."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from flash.domain.agent.agent import Agent
from flash.domain.shared.identifiers import EntityId


@runtime_checkable
class AgentRepository(Protocol):
    def get(self, agent_id: EntityId) -> Agent | None: ...

    def get_by_user_id(self, user_id: EntityId) -> Agent | None: ...

    def get_for_update(self, agent_id: EntityId) -> Agent:
        """Charge l'agent avec un verrou pessimiste. Lève ``KeyError`` s'il n'existe pas."""
        ...

    def list_with_commission_owed(self, threshold_minor: int) -> list[Agent]:
        """Agents ``ACTIVE`` dont la commission due atteint ``threshold_minor``."""
        ...

    def add(self, agent: Agent) -> None: ...

    def save(self, agent: Agent) -> None: ...


__all__ = ["AgentRepository"]
