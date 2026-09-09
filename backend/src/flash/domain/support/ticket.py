"""Entités back-office (BE-075) : ``SupportNote`` (annotation libre sur un compte) et
``SupportTicket`` (demande de support suivie). Volontairement simples — pas d'événements
de domaine : la traçabilité passe par le registre d'audit chaîné.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from flash.domain.shared.errors import InvalidInput
from flash.domain.shared.identifiers import EntityId

_MAX_NOTE = 2_000
_MAX_SUBJECT = 160


class TicketStatus(StrEnum):
    OPEN = "OPEN"
    PENDING = "PENDING"
    RESOLVED = "RESOLVED"
    CLOSED = "CLOSED"

    @property
    def is_terminal(self) -> bool:
        return self in (TicketStatus.RESOLVED, TicketStatus.CLOSED)


class SupportNote:
    def __init__(
        self,
        *,
        id: EntityId,
        subject_user_id: EntityId,
        author: str,
        body: str,
        created_at: datetime,
    ) -> None:
        cleaned = body.strip()
        if not cleaned:
            raise InvalidInput("Une note ne peut pas être vide.")
        if len(cleaned) > _MAX_NOTE:
            raise InvalidInput("Note trop longue (2000 caractères max).")
        self.id = id
        self.subject_user_id = subject_user_id
        self.author = author
        self.body = cleaned
        self.created_at = created_at

    def __repr__(self) -> str:
        return f"SupportNote(subject={self.subject_user_id!s}, author={self.author!r})"


class SupportTicket:
    def __init__(
        self,
        *,
        id: EntityId,
        subject_user_id: EntityId,
        opened_by: str,
        subject: str,
        status: TicketStatus,
        created_at: datetime,
        updated_at: datetime,
        last_actor: str | None = None,
    ) -> None:
        cleaned = subject.strip()
        if not cleaned:
            raise InvalidInput("Le sujet du ticket est requis.")
        if len(cleaned) > _MAX_SUBJECT:
            raise InvalidInput("Sujet trop long (160 caractères max).")
        self.id = id
        self.subject_user_id = subject_user_id
        self.opened_by = opened_by
        self.subject = cleaned
        self.status = status
        self.created_at = created_at
        self.updated_at = updated_at
        self.last_actor = last_actor

    @classmethod
    def open(
        cls,
        *,
        ticket_id: EntityId,
        subject_user_id: EntityId,
        opened_by: str,
        subject: str,
        now: datetime,
    ) -> SupportTicket:
        return cls(
            id=ticket_id,
            subject_user_id=subject_user_id,
            opened_by=opened_by,
            subject=subject,
            status=TicketStatus.OPEN,
            created_at=now,
            updated_at=now,
            last_actor=opened_by,
        )

    def transition_to(self, status: TicketStatus, *, actor: str, now: datetime) -> None:
        if self.status.is_terminal and status is not TicketStatus.OPEN:
            raise InvalidInput("Ce ticket est clôturé ; il faut le rouvrir d'abord.")
        self.status = status
        self.last_actor = actor
        self.updated_at = now

    def __repr__(self) -> str:
        return f"SupportTicket(id={self.id!s}, status={self.status.value})"


__all__ = ["SupportNote", "SupportTicket", "TicketStatus"]
