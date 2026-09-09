"""``SqlAlchemyAuditLog`` — registre d'audit append-only, chaîné par hachage (BE-062).

Sessions propres (hors Unit of Work applicative) : une écriture d'audit ne doit jamais
être annulée avec l'opération métier — elle constate un fait déjà décidé côté back-office.
Le numéro de séquence est protégé par une contrainte d'unicité ; les écritures
back-office sont rares, la sérialisation naïve (max(sequence) + 1) suffit.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from flash.domain.audit.entry import GENESIS_HASH, AuditEntry, verify_chain
from flash.domain.shared.ports import IdGenerator
from flash.infrastructure.db.models import AuditEntryModel


def _to_domain(model: AuditEntryModel) -> AuditEntry:
    return AuditEntry(
        id=model.id,
        sequence=model.sequence,
        actor=model.actor,
        role=model.role,
        action=model.action,
        resource_type=model.resource_type,
        resource_id=model.resource_id,
        before=model.before,
        after=model.after,
        occurred_at=model.occurred_at,
        prev_hash=model.prev_hash,
        entry_hash=model.entry_hash,
    )


class SqlAlchemyAuditLog:
    def __init__(self, session_factory: sessionmaker[Session], ids: IdGenerator) -> None:
        self._session_factory = session_factory
        self._ids = ids

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
        with self._session_factory() as session:
            last = session.scalars(
                select(AuditEntryModel).order_by(AuditEntryModel.sequence.desc()).limit(1)
            ).first()
            sequence = (last.sequence + 1) if last is not None else 1
            prev_hash = last.entry_hash if last is not None else GENESIS_HASH
            entry = AuditEntry.create(
                id=str(self._ids.new_id()),
                sequence=sequence,
                actor=actor,
                role=role,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                before=dict(before) if before is not None else None,
                after=dict(after) if after is not None else None,
                occurred_at=now,
                prev_hash=prev_hash,
            )
            session.add(
                AuditEntryModel(
                    id=entry.id,
                    sequence=entry.sequence,
                    actor=entry.actor,
                    role=entry.role,
                    action=entry.action,
                    resource_type=entry.resource_type,
                    resource_id=entry.resource_id,
                    before=entry.before,
                    after=entry.after,
                    occurred_at=entry.occurred_at,
                    prev_hash=entry.prev_hash,
                    entry_hash=entry.entry_hash,
                )
            )
            session.commit()
        return entry

    def recent(
        self, *, limit: int = 100, before_sequence: int | None = None
    ) -> list[AuditEntry]:
        with self._session_factory() as session:
            stmt = select(AuditEntryModel).order_by(AuditEntryModel.sequence.desc())
            if before_sequence is not None:
                stmt = stmt.where(AuditEntryModel.sequence < before_sequence)
            stmt = stmt.limit(min(max(limit, 1), 500))
            return [_to_domain(m) for m in session.scalars(stmt)]

    def verify(self) -> bool:
        with self._session_factory() as session:
            rows = session.scalars(
                select(AuditEntryModel).order_by(AuditEntryModel.sequence.asc())
            )
            return verify_chain([_to_domain(m) for m in rows])


__all__ = ["SqlAlchemyAuditLog"]
