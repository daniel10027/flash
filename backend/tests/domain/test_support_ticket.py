"""Tests des entités back-office ``SupportNote`` / ``SupportTicket`` (BE-075)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from flash.domain.shared.errors import InvalidInput
from flash.domain.shared.identifiers import EntityId
from flash.domain.support.ticket import SupportNote, SupportTicket, TicketStatus

T0 = datetime(2026, 1, 1, tzinfo=UTC)
NID = EntityId(str(UUID(int=1)))
TID = EntityId(str(UUID(int=2)))
UID = EntityId(str(UUID(int=3)))


class TestSupportNote:
    def test_trims_body(self) -> None:
        note = SupportNote(
            id=NID, subject_user_id=UID, author="key:support", body="  à vérifier  ", created_at=T0
        )
        assert note.body == "à vérifier"

    def test_empty_body_rejected(self) -> None:
        with pytest.raises(InvalidInput, match="vide"):
            SupportNote(id=NID, subject_user_id=UID, author="a", body="   ", created_at=T0)

    def test_too_long_body_rejected(self) -> None:
        with pytest.raises(InvalidInput, match="trop longue"):
            SupportNote(
                id=NID, subject_user_id=UID, author="a", body="x" * 2001, created_at=T0
            )

    def test_repr(self) -> None:
        note = SupportNote(id=NID, subject_user_id=UID, author="a", body="b", created_at=T0)
        assert "SupportNote(" in repr(note)


class TestTicketStatus:
    @pytest.mark.parametrize(
        ("status", "terminal"),
        [
            (TicketStatus.OPEN, False),
            (TicketStatus.PENDING, False),
            (TicketStatus.RESOLVED, True),
            (TicketStatus.CLOSED, True),
        ],
    )
    def test_is_terminal(self, status: TicketStatus, terminal: bool) -> None:
        assert status.is_terminal is terminal


class TestSupportTicket:
    def _ticket(self) -> SupportTicket:
        return SupportTicket.open(
            ticket_id=TID,
            subject_user_id=UID,
            opened_by="key:support",
            subject="Litige retrait",
            now=T0,
        )

    def test_open_defaults(self) -> None:
        ticket = self._ticket()
        assert ticket.status is TicketStatus.OPEN
        assert ticket.last_actor == "key:support"
        assert ticket.created_at == ticket.updated_at

    def test_empty_subject_rejected(self) -> None:
        with pytest.raises(InvalidInput, match="sujet"):
            SupportTicket.open(
                ticket_id=TID, subject_user_id=UID, opened_by="a", subject="  ", now=T0
            )

    def test_too_long_subject_rejected(self) -> None:
        with pytest.raises(InvalidInput, match="trop long"):
            SupportTicket.open(
                ticket_id=TID,
                subject_user_id=UID,
                opened_by="a",
                subject="x" * 161,
                now=T0,
            )

    def test_transition_updates_actor_and_timestamp(self) -> None:
        ticket = self._ticket()
        later = datetime(2026, 1, 2, tzinfo=UTC)
        ticket.transition_to(TicketStatus.PENDING, actor="key:compliance", now=later)
        assert ticket.status is TicketStatus.PENDING
        assert ticket.last_actor == "key:compliance"
        assert ticket.updated_at == later

    def test_cannot_leave_closed_except_reopen(self) -> None:
        ticket = self._ticket()
        ticket.transition_to(TicketStatus.CLOSED, actor="a", now=T0)
        with pytest.raises(InvalidInput, match="rouvrir"):
            ticket.transition_to(TicketStatus.PENDING, actor="a", now=T0)
        ticket.transition_to(TicketStatus.OPEN, actor="a", now=T0)
        assert ticket.status is TicketStatus.OPEN

    def test_repr(self) -> None:
        assert "status=OPEN" in repr(self._ticket())
