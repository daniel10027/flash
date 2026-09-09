"""Tests de l'agrégat ``ComplianceAlert`` (BE-076)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from flash.domain.compliance.alert import AlertKind, AlertStatus, ComplianceAlert
from flash.domain.shared.errors import InvalidAccountState, InvalidInput
from flash.domain.shared.identifiers import EntityId

T0 = datetime(2026, 1, 1, tzinfo=UTC)
AID = EntityId(str(UUID(int=1)))
UID = EntityId(str(UUID(int=2)))


def _alert(kind: AlertKind = AlertKind.VELOCITY) -> ComplianceAlert:
    return ComplianceAlert.open(
        alert_id=AID,
        user_id=UID,
        kind=kind,
        score=70,
        detail={"count": 22},
        window_key="vel:2026-01-01",
        now=T0,
    )


class TestAlertStatus:
    @pytest.mark.parametrize(
        ("status", "resolved"),
        [
            (AlertStatus.OPEN, False),
            (AlertStatus.REVIEWING, False),
            (AlertStatus.CLEARED, True),
            (AlertStatus.ESCALATED, True),
        ],
    )
    def test_is_resolved(self, status: AlertStatus, resolved: bool) -> None:
        assert status.is_resolved is resolved


class TestComplianceAlert:
    def test_open_records_event(self) -> None:
        alert = _alert()
        assert alert.status is AlertStatus.OPEN
        assert [e.name for e in alert.pull_events()] == ["ComplianceAlertOpened"]

    def test_score_out_of_range_rejected(self) -> None:
        with pytest.raises(InvalidInput, match="score"):
            ComplianceAlert.open(
                alert_id=AID,
                user_id=UID,
                kind=AlertKind.MANUAL,
                score=200,
                detail={},
                window_key="w",
                now=T0,
            )

    def test_start_review_then_clear(self) -> None:
        alert = _alert()
        alert.pull_events()
        alert.start_review(analyst="key:compliance", now=T0)
        assert alert.status is AlertStatus.REVIEWING
        alert.clear(analyst="key:compliance", note="  faux positif  ", now=T0)
        assert alert.status is AlertStatus.CLEARED
        assert alert.resolution_note == "faux positif"
        assert alert.resolved_at == T0
        assert [e.name for e in alert.pull_events()] == ["ComplianceAlertResolved"]

    def test_clear_from_open_directly(self) -> None:
        alert = _alert()
        alert.clear(analyst="a", note="", now=T0)
        assert alert.status is AlertStatus.CLEARED
        assert alert.resolution_note is None

    def test_escalate_requires_note(self) -> None:
        alert = _alert()
        with pytest.raises(InvalidInput, match="motif"):
            alert.escalate(analyst="a", note="  ", now=T0)

    def test_escalate_records_event(self) -> None:
        alert = _alert()
        alert.pull_events()
        alert.escalate(analyst="key:compliance", note="STR déposée", now=T0)
        assert alert.status is AlertStatus.ESCALATED
        assert [e.name for e in alert.pull_events()] == ["ComplianceAlertEscalated"]

    def test_start_review_only_from_open(self) -> None:
        alert = _alert()
        alert.clear(analyst="a", note="", now=T0)
        with pytest.raises(InvalidAccountState, match="plus ouverte"):
            alert.start_review(analyst="a", now=T0)

    def test_cannot_re_resolve(self) -> None:
        alert = _alert()
        alert.escalate(analyst="a", note="x", now=T0)
        with pytest.raises(InvalidAccountState, match="déjà résolue"):
            alert.clear(analyst="a", note="", now=T0)

    def test_repr(self) -> None:
        assert "kind=VELOCITY" in repr(_alert())
