"""Registre d'audit en mémoire pour les tests — même chaînage par hachage."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from flash.domain.audit.entry import GENESIS_HASH, AuditEntry, verify_chain


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
        rows = list(reversed(self._entries))
        if before_sequence is not None:
            rows = [e for e in rows if e.sequence < before_sequence]
        return rows[: min(max(limit, 1), 500)]

    def verify(self) -> bool:
        return verify_chain(list(self._entries))


__all__ = ["InMemoryAuditLog"]
