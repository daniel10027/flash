"""Registre d'audit en mémoire pour les tests — même chaînage par hachage.

Permet aussi d'injecter des entrées corrompues (``_entries``) pour tester le contrôle
d'intégrité.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from flash.domain.audit.entry import (
    GENESIS_HASH,
    AuditEntry,
    ChainReport,
    audit_chain_report,
)
from flash.domain.audit.ports import AuditFilter


class InMemoryAuditLog:
    def __init__(self) -> None:
        self._entries: list[AuditEntry] = []
        self._seq = 0

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
        self._seq += 1
        prev = self._entries[-1].entry_hash if self._entries else GENESIS_HASH
        entry = AuditEntry.create(
            id=f"audit-{self._seq}",
            sequence=self._seq,
            actor=actor,
            role=role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            before=dict(before) if before is not None else None,
            after=dict(after) if after is not None else None,
            occurred_at=now,
            prev_hash=prev,
        )
        self._entries.append(entry)
        return entry

    def recent(
        self, *, limit: int = 100, before_sequence: int | None = None
    ) -> list[AuditEntry]:
        return self.query(AuditFilter(limit=limit, before_sequence=before_sequence))

    def query(self, filters: AuditFilter, /) -> list[AuditEntry]:
        rows = list(reversed(self._entries))
        if filters.actor is not None:
            rows = [e for e in rows if e.actor == filters.actor]
        if filters.action is not None:
            rows = [e for e in rows if e.action == filters.action]
        if filters.resource_type is not None:
            rows = [e for e in rows if e.resource_type == filters.resource_type]
        if filters.resource_id is not None:
            rows = [e for e in rows if e.resource_id == filters.resource_id]
        if filters.start is not None:
            rows = [e for e in rows if e.occurred_at >= filters.start]
        if filters.end is not None:
            rows = [e for e in rows if e.occurred_at < filters.end]
        if filters.before_sequence is not None:
            rows = [e for e in rows if e.sequence < filters.before_sequence]
        return rows[: min(max(filters.limit, 1), 500)]

    def verify(self) -> bool:
        return self.verify_report().intact

    def verify_report(self) -> ChainReport:
        return audit_chain_report(list(self._entries))


__all__ = ["InMemoryAuditLog"]
