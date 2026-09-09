"""Port du sous-domaine épargne (agrégat ``SavingsPlan``)."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from flash.domain.savings.plan import SavingsPlan
from flash.domain.shared.identifiers import EntityId


@runtime_checkable
class SavingsPlanRepository(Protocol):
    def get(self, plan_id: EntityId) -> SavingsPlan | None: ...

    def get_for_update(self, plan_id: EntityId) -> SavingsPlan:
        """Plan avec verrou pessimiste. Lève ``KeyError`` si absent."""
        ...

    def list_for_user(self, user_id: EntityId) -> list[SavingsPlan]: ...

    def list_active(self, *, limit: int = 500, after: EntityId | None = None) -> list[SavingsPlan]:
        """Plans ``ACTIVE``, triés par id (pagination des jobs)."""
        ...

    def list_contributions_due(self, now: datetime, *, limit: int = 500) -> list[SavingsPlan]:
        """Plans ``ACTIVE`` dont un versement programmé est échu (job BE-052)."""
        ...

    def add(self, plan: SavingsPlan) -> None: ...

    def save(self, plan: SavingsPlan) -> None: ...


__all__ = ["SavingsPlanRepository"]
