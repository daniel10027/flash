"""Port du registre d'audit (append-only)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from flash.domain.audit.entry import AuditEntry


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

    def verify(self) -> bool:
        """Vrai si toute la chaîne persistée est intègre."""
        ...


__all__ = ["AuditLog"]
