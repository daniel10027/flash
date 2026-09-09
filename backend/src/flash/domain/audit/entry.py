"""``AuditEntry`` — une ligne du registre d'audit, immuable et **chaînée**.

Chaque entrée porte le hachage de la précédente (``prev_hash``) et son propre hachage
(``entry_hash``) calculé sur son contenu canonique. Toute altération d'une ligne (ou
suppression / réordonnancement) casse la chaîne : ``AuditLog.verify()`` la détecte.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any

GENESIS_HASH = "0" * 64


def compute_entry_hash(
    *,
    sequence: int,
    actor: str,
    role: str,
    action: str,
    resource_type: str,
    resource_id: str,
    before: Mapping[str, Any] | None,
    after: Mapping[str, Any] | None,
    occurred_at: datetime,
    prev_hash: str,
) -> str:
    payload = json.dumps(
        {
            "sequence": sequence,
            "actor": actor,
            "role": role,
            "action": action,
            "resource_type": resource_type,
            "resource_id": resource_id,
            "before": before,
            "after": after,
            "occurred_at": occurred_at.isoformat(),
            "prev_hash": prev_hash,
        },
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
        default=str,
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class AuditEntry:
    id: str
    sequence: int
    actor: str
    role: str
    action: str
    resource_type: str
    resource_id: str
    before: Mapping[str, Any] | None
    after: Mapping[str, Any] | None
    occurred_at: datetime
    prev_hash: str
    entry_hash: str

    @classmethod
    def create(
        cls,
        *,
        id: str,
        sequence: int,
        actor: str,
        role: str,
        action: str,
        resource_type: str,
        resource_id: str,
        before: Mapping[str, Any] | None,
        after: Mapping[str, Any] | None,
        occurred_at: datetime,
        prev_hash: str,
    ) -> AuditEntry:
        return cls(
            id=id,
            sequence=sequence,
            actor=actor,
            role=role,
            action=action,
            resource_type=resource_type,
            resource_id=resource_id,
            before=before,
            after=after,
            occurred_at=occurred_at,
            prev_hash=prev_hash,
            entry_hash=compute_entry_hash(
                sequence=sequence,
                actor=actor,
                role=role,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                before=before,
                after=after,
                occurred_at=occurred_at,
                prev_hash=prev_hash,
            ),
        )

    @property
    def recomputed_hash(self) -> str:
        return compute_entry_hash(
            sequence=self.sequence,
            actor=self.actor,
            role=self.role,
            action=self.action,
            resource_type=self.resource_type,
            resource_id=self.resource_id,
            before=self.before,
            after=self.after,
            occurred_at=self.occurred_at,
            prev_hash=self.prev_hash,
        )

    @property
    def is_intact(self) -> bool:
        return self.entry_hash == self.recomputed_hash

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "sequence": self.sequence,
            "actor": self.actor,
            "role": self.role,
            "action": self.action,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "before": dict(self.before) if self.before is not None else None,
            "after": dict(self.after) if self.after is not None else None,
            "occurred_at": self.occurred_at.isoformat(),
            "prev_hash": self.prev_hash,
            "entry_hash": self.entry_hash,
        }


def verify_chain(entries: list[AuditEntry]) -> bool:
    """Vrai si la liste (triée par ``sequence`` croissant) forme une chaîne intègre."""
    expected_prev = GENESIS_HASH
    expected_seq = 1
    for entry in entries:
        if entry.sequence != expected_seq:
            return False
        if entry.prev_hash != expected_prev:
            return False
        if not entry.is_intact:
            return False
        expected_prev = entry.entry_hash
        expected_seq += 1
    return True


__all__ = ["GENESIS_HASH", "AuditEntry", "compute_entry_hash", "verify_chain"]
