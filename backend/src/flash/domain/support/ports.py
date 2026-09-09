"""Ports back-office (BE-075)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from flash.domain.shared.identifiers import EntityId
from flash.domain.support.ticket import SupportNote, SupportTicket


@runtime_checkable
class SupportNoteRepository(Protocol):
    def list_for_user(self, user_id: EntityId, *, limit: int = 100) -> list[SupportNote]: ...

    def add(self, note: SupportNote) -> None: ...


@runtime_checkable
class SupportTicketRepository(Protocol):
    def get(self, ticket_id: EntityId) -> SupportTicket | None: ...

    def list_recent(
        self, *, status: str | None = None, limit: int = 100
    ) -> list[SupportTicket]: ...

    def list_for_user(self, user_id: EntityId, *, limit: int = 100) -> list[SupportTicket]: ...

    def add(self, ticket: SupportTicket) -> None: ...

    def save(self, ticket: SupportTicket) -> None: ...


__all__ = ["SupportNoteRepository", "SupportTicketRepository"]
