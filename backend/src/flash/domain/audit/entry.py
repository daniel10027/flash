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


@dataclass(frozen=True, slots=True)
class ChainReport:
    """Résultat détaillé du contrôle d'intégrité de la chaîne d'audit."""

    intact: bool
    checked: int
    broken_at: int | None  # ``sequence`` de la première entrée fautive
    reason: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "intact": self.intact,
            "checked": self.checked,
            "broken_at": self.broken_at,
            "reason": self.reason,
        }


def audit_chain_report(entries: list[AuditEntry]) -> ChainReport:
    """Contrôle la chaîne (entrées triées par ``sequence`` croissant) et localise la
    première rupture : trou / réordonnancement de séquence, ``prev_hash`` incohérent
    (suppression, insertion) ou contenu altéré."""
    expected_prev = GENESIS_HASH
    expected_seq = 1
    checked = 0
    for entry in entries:
        checked += 1
        if entry.sequence != expected_seq:
            return ChainReport(
                intact=False,
                checked=checked,
                broken_at=entry.sequence,
                reason=f"séquence attendue {expected_seq}, trouvée {entry.sequence}",
            )
        if entry.prev_hash != expected_prev:
            return ChainReport(
                intact=False,
                checked=checked,
                broken_at=entry.sequence,
                reason="prev_hash ne correspond pas au hachage de l'entrée précédente",
            )
        if not entry.is_intact:
            return ChainReport(
                intact=False,
                checked=checked,
                broken_at=entry.sequence,
                reason="entry_hash ne correspond pas au contenu (entrée altérée)",
            )
        expected_prev = entry.entry_hash
        expected_seq += 1
    return ChainReport(intact=True, checked=checked, broken_at=None, reason=None)


def verify_chain(entries: list[AuditEntry]) -> bool:
    """Vrai si la liste (triée par ``sequence`` croissant) forme une chaîne intègre."""
    return audit_chain_report(entries).intact


__all__ = [
    "GENESIS_HASH",
    "AuditEntry",
    "ChainReport",
    "audit_chain_report",
    "compute_entry_hash",
    "verify_chain",
]
