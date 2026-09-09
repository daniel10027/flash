"""Port du sous-domaine conformité (BE-076)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from flash.domain.compliance.alert import ComplianceAlert
from flash.domain.shared.identifiers import EntityId


@runtime_checkable
class ComplianceAlertRepository(Protocol):
    def get(self, alert_id: EntityId) -> ComplianceAlert | None: ...

    def exists_window(self, user_id: EntityId, kind: str, window_key: str) -> bool:
        """Vrai si une alerte de ce type existe déjà pour cette fenêtre (dédoublonnage)."""
        ...

    def list_open(self, *, limit: int = 200) -> list[ComplianceAlert]: ...

    def list_between(self, start: str, end: str) -> list[ComplianceAlert]:
        """Alertes dont ``created_at`` (ISO) est dans ``[start, end)`` — pour l'export STR."""
        ...

    def list_by_status(self, status: str, *, limit: int = 200) -> list[ComplianceAlert]: ...

    def add(self, alert: ComplianceAlert) -> None: ...

    def save(self, alert: ComplianceAlert) -> None: ...


__all__ = ["ComplianceAlertRepository"]
