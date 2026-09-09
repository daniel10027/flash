"""Agrégat ``ComplianceAlert`` (BE-076) — une alerte AML sur un compte.

Ouverte par la détection automatique (seuil CTR, structuration, vélocité) ou à la main
par un analyste. ``OPEN`` → ``REVIEWING`` → ``CLEARED`` (faux positif) / ``ESCALATED``
(déclaration STR + blocage préventif décidé au niveau applicatif).
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Any

from flash.domain.compliance.events import (
    ComplianceAlertEscalated,
    ComplianceAlertOpened,
    ComplianceAlertResolved,
)
from flash.domain.shared.errors import InvalidAccountState, InvalidInput
from flash.domain.shared.events import EventRecorder
from flash.domain.shared.identifiers import EntityId


class AlertKind(StrEnum):
    CTR_THRESHOLD = "CTR_THRESHOLD"  # transaction unitaire au-dessus du seuil déclaratif
    STRUCTURING = "STRUCTURING"  # fractionnement sous le seuil
    VELOCITY = "VELOCITY"  # trop d'opérations / trop de volume sur une fenêtre
    MANUAL = "MANUAL"  # ouverte par un analyste


class AlertStatus(StrEnum):
    OPEN = "OPEN"
    REVIEWING = "REVIEWING"
    CLEARED = "CLEARED"
    ESCALATED = "ESCALATED"

    @property
    def is_resolved(self) -> bool:
        return self in (AlertStatus.CLEARED, AlertStatus.ESCALATED)


class ComplianceAlert(EventRecorder):
    def __init__(
        self,
        *,
        id: EntityId,
        user_id: EntityId,
        kind: AlertKind,
        status: AlertStatus,
        score: int,
        detail: dict[str, Any],
        created_at: datetime,
        window_key: str,
        reviewed_by: str | None = None,
        resolution_note: str | None = None,
        resolved_at: datetime | None = None,
    ) -> None:
        super().__init__()
        if not 0 <= score <= 100:
            raise InvalidInput("Le score d'alerte doit être entre 0 et 100.")
        self.id = id
        self.user_id = user_id
        self.kind = kind
        self.status = status
        self.score = score
        self.detail = detail
        self.created_at = created_at
        self.window_key = window_key
        self.reviewed_by = reviewed_by
        self.resolution_note = resolution_note
        self.resolved_at = resolved_at

    @classmethod
    def open(
        cls,
        *,
        alert_id: EntityId,
        user_id: EntityId,
        kind: AlertKind,
        score: int,
        detail: dict[str, Any],
        window_key: str,
        now: datetime,
    ) -> ComplianceAlert:
        alert = cls(
            id=alert_id,
            user_id=user_id,
            kind=kind,
            status=AlertStatus.OPEN,
            score=score,
            detail=detail,
            created_at=now,
            window_key=window_key,
        )
        alert.record_event(
            ComplianceAlertOpened(
                occurred_at=now,
                aggregate_id=str(alert_id),
                user_id=str(user_id),
                kind=kind.value,
                score=score,
            )
        )
        return alert

    def start_review(self, *, analyst: str, now: datetime) -> None:
        self._ensure_open()
        self.status = AlertStatus.REVIEWING
        self.reviewed_by = analyst

    def clear(self, *, analyst: str, note: str, now: datetime) -> None:
        self._ensure_actionable()
        self.status = AlertStatus.CLEARED
        self.reviewed_by = analyst
        self.resolution_note = note.strip() or None
        self.resolved_at = now
        self.record_event(
            ComplianceAlertResolved(
                occurred_at=now,
                aggregate_id=str(self.id),
                user_id=str(self.user_id),
                outcome="CLEARED",
            )
        )

    def escalate(self, *, analyst: str, note: str, now: datetime) -> None:
        self._ensure_actionable()
        if not note.strip():
            raise InvalidInput("Un motif est requis pour escalader une alerte.")
        self.status = AlertStatus.ESCALATED
        self.reviewed_by = analyst
        self.resolution_note = note.strip()
        self.resolved_at = now
        self.record_event(
            ComplianceAlertEscalated(
                occurred_at=now,
                aggregate_id=str(self.id),
                user_id=str(self.user_id),
                note=note.strip(),
            )
        )

    def _ensure_open(self) -> None:
        if self.status is not AlertStatus.OPEN:
            raise InvalidAccountState(
                "Cette alerte n'est plus ouverte.", status=self.status.value
            )

    def _ensure_actionable(self) -> None:
        if self.status.is_resolved:
            raise InvalidAccountState(
                "Cette alerte est déjà résolue.", status=self.status.value
            )

    def __repr__(self) -> str:
        return (
            f"ComplianceAlert(kind={self.kind.value}, status={self.status.value}, "
            f"score={self.score})"
        )


__all__ = ["AlertKind", "AlertStatus", "ComplianceAlert"]
