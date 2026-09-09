"""Port du registre d'audit (append-only)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from flash.domain.audit.entry import AuditEntry, ChainReport


@dataclass(frozen=True, slots=True)
class AuditFilter:
    """Critères de consultation du registre (tous optionnels, combinés en ET)."""

    actor: str | None = None
    action: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    start: datetime | None = None  # borne inférieure incluse sur ``occurred_at``
    end: datetime | None = None  # borne supérieure exclue sur ``occurred_at``
    limit: int = 100
    before_sequence: int | None = None


@runtime_checkable
class AuditLog(Protocol):
    def append(
        self,
        *,
        actor: str,
        role: str,
        action: str,
        resource_type: str,
        resource_id: str,
        before: Mapping[str, Any] | None,
        after: Mapping[str, Any] | None,
        now: datetime,
    ) -> AuditEntry:
        """Ajoute une entrée en fin de chaîne et la renvoie."""
        ...

    def recent(
        self, *, limit: int = 100, before_sequence: int | None = None
    ) -> list[AuditEntry]:
        """Entrées les plus récentes d'abord (curseur descendant sur ``sequence``)."""
        ...

    def query(self, filters: AuditFilter, /) -> list[AuditEntry]:
        """Entrées correspondant aux ``filters`` (qui / quoi / ressource / période),
        les plus récentes d'abord, curseur descendant sur ``sequence``."""
        ...

    def verify(self) -> bool:
        """Vrai si toute la chaîne persistée est intègre."""
        ...

    def verify_report(self) -> ChainReport:
        """Contrôle d'intégrité détaillé : localise la première rupture éventuelle."""
        ...


__all__ = ["AuditFilter", "AuditLog"]
