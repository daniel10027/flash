"""Registre d'audit consultable (BE-078).

Le registre est déjà **append-only + chaîné par hachage** (BE-062). Ce module ajoute :

* ``QueryAuditLog`` — lecture filtrée (qui / quoi / ressource / période) avec curseur
  descendant sur ``sequence`` ;
* ``VerifyAuditChain`` — contrôle d'intégrité de toute la chaîne, avec localisation de
  la première rupture éventuelle.

Aucune écriture : les seules mutations du registre passent par ``AuditLog.append`` au
fil des actions sensibles.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from flash.application.use_case import Command, UseCase
from flash.domain.audit.entry import AuditEntry, ChainReport
from flash.domain.audit.ports import AuditFilter, AuditLog
from flash.domain.shared.errors import InvalidInput

_MAX_LIMIT = 500
_DEFAULT_LIMIT = 100


def _parse_instant(raw: str, *, field: str) -> datetime:
    try:
        value = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise InvalidInput(f"`{field}` : date/heure ISO 8601 attendue.") from exc
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


@dataclass(frozen=True, slots=True)
class QueryAuditLogCommand(Command):
    actor: str | None = None
    action: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    start: str | None = None
    end: str | None = None
    limit: int = _DEFAULT_LIMIT
    before_sequence: int | None = None
    verify: bool = False


@dataclass(frozen=True, slots=True)
class AuditPage:
    entries: list[AuditEntry]
    chain: ChainReport | None  # présent si ``verify`` demandé

    def to_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"entries": [e.to_dict() for e in self.entries]}
        if self.chain is not None:
            payload["chain"] = self.chain.to_dict()
            payload["intact"] = self.chain.intact  # raccourci rétro-compatible
        return payload


class QueryAuditLog(UseCase[QueryAuditLogCommand, AuditPage]):
    def __init__(self, *, audit: AuditLog) -> None:
        self._audit = audit

    def execute(self, command: QueryAuditLogCommand) -> AuditPage:
        start = _parse_instant(command.start, field="start") if command.start else None
        end = _parse_instant(command.end, field="end") if command.end else None
        if start is not None and end is not None and end <= start:
            raise InvalidInput("`end` doit être postérieur à `start`.")
        limit = max(1, min(command.limit, _MAX_LIMIT))
        entries = self._audit.query(
            AuditFilter(
                actor=command.actor or None,
                action=command.action or None,
                resource_type=command.resource_type or None,
                resource_id=command.resource_id or None,
                start=start,
                end=end,
                limit=limit,
                before_sequence=command.before_sequence,
            )
        )
        chain = self._audit.verify_report() if command.verify else None
        return AuditPage(entries=entries, chain=chain)


@dataclass(frozen=True, slots=True)
class VerifyAuditChainCommand(Command):
    pass


class VerifyAuditChain(UseCase[VerifyAuditChainCommand, ChainReport]):
    def __init__(self, *, audit: AuditLog) -> None:
        self._audit = audit

    def execute(self, command: VerifyAuditChainCommand) -> ChainReport:
        return self._audit.verify_report()


__all__ = [
    "AuditPage",
    "QueryAuditLog",
    "QueryAuditLogCommand",
    "VerifyAuditChain",
    "VerifyAuditChainCommand",
]
