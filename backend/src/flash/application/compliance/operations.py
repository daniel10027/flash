"""Conformité (BE-076) : file d'alertes AML, revue (clear / escalade + blocage
préventif), ouverture manuelle, export STR/CTR au format CSV.

Escalader une alerte **gèle le compte** (blocage préventif) et écrit une entrée d'audit.
Toute revue est auditée.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from flash.application.services import AppServices
from flash.application.transaction import execute_in_uow
from flash.application.unit_of_work import WorkUnitOfWork
from flash.application.use_case import Command, UseCase
from flash.domain.audit.ports import AuditLog
from flash.domain.compliance.alert import AlertKind, AlertStatus, ComplianceAlert
from flash.domain.shared.errors import InvalidInput
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.ports import Clock


@dataclass(frozen=True, slots=True)
class AlertView:
    alert_id: str
    user_id: str
    kind: str
    status: str
    score: int
    detail: dict[str, Any]
    created_at: str
    reviewed_by: str | None
    resolution_note: str | None
    resolved_at: str | None

    @classmethod
    def of(cls, alert: ComplianceAlert) -> AlertView:
        return cls(
            alert_id=str(alert.id),
            user_id=str(alert.user_id),
            kind=alert.kind.value,
            status=alert.status.value,
            score=alert.score,
            detail=alert.detail,
            created_at=alert.created_at.isoformat(),
            reviewed_by=alert.reviewed_by,
            resolution_note=alert.resolution_note,
            resolved_at=alert.resolved_at.isoformat() if alert.resolved_at else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "alert_id": self.alert_id,
            "user_id": self.user_id,
            "kind": self.kind,
            "status": self.status,
            "score": self.score,
            "detail": self.detail,
            "created_at": self.created_at,
            "reviewed_by": self.reviewed_by,
            "resolution_note": self.resolution_note,
            "resolved_at": self.resolved_at,
        }


@dataclass(frozen=True, slots=True)
class ListComplianceAlertsCommand(Command):
    status: str | None = None


class ListComplianceAlerts(
    UseCase[ListComplianceAlertsCommand, list[AlertView]]
):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: ListComplianceAlertsCommand) -> list[AlertView]:
        if command.status is not None:
            try:
                AlertStatus(command.status)
            except ValueError as exc:
                raise InvalidInput("Statut d'alerte inconnu.") from exc
        with self._services.uow() as uow:
            if command.status is None:
                rows = uow.compliance_alerts.list_open()
            else:
                rows = uow.compliance_alerts.list_by_status(command.status)
            return [AlertView.of(a) for a in rows]


@dataclass(frozen=True, slots=True)
class RaiseManualAlertCommand(Command):
    user_id: str
    reason: str
    analyst: str
    role: str


class RaiseManualAlert(UseCase[RaiseManualAlertCommand, AlertView]):
    def __init__(self, *, services: AppServices, audit: AuditLog, clock: Clock) -> None:
        self._services = services
        self._audit = audit
        self._clock = clock

    def execute(self, command: RaiseManualAlertCommand) -> AlertView:
        if not command.reason.strip():
            raise InvalidInput("Un motif est requis.")
        now = self._clock.now()
        alert_id = self._services.ids.new_id()
        captured: list[AlertView] = []

        def work(uow: WorkUnitOfWork) -> None:
            try:
                user_id = EntityId(command.user_id)
            except ValueError as exc:
                raise InvalidInput("Compte introuvable.") from exc
            if uow.users.get(user_id) is None:
                raise InvalidInput("Compte introuvable.")
            alert = ComplianceAlert.open(
                alert_id=alert_id,
                user_id=user_id,
                kind=AlertKind.MANUAL,
                score=60,
                detail={"reason": command.reason.strip()},
                window_key=f"manual:{alert_id}",
                now=now,
            )
            uow.compliance_alerts.add(alert)
            captured.append(AlertView.of(alert))
            self._audit.append(
                actor=command.analyst,
                role=command.role,
                action="aml.alert.manual",
                resource_type="compliance_alert",
                resource_id=str(alert_id),
                before=None,
                after={"user_id": command.user_id, "reason": command.reason.strip()},
                now=now,
            )

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


@dataclass(frozen=True, slots=True)
class ReviewComplianceAlertCommand(Command):
    alert_id: str
    decision: str  # "clear" | "escalate"
    note: str
    analyst: str
    role: str


class ReviewComplianceAlert(UseCase[ReviewComplianceAlertCommand, AlertView]):
    """``clear`` = faux positif. ``escalate`` = STR + **gel préventif du compte**."""

    def __init__(self, *, services: AppServices, audit: AuditLog, clock: Clock) -> None:
        self._services = services
        self._audit = audit
        self._clock = clock

    def execute(self, command: ReviewComplianceAlertCommand) -> AlertView:
        if command.decision not in ("clear", "escalate"):
            raise InvalidInput("Décision inconnue (clear | escalate).")
        now = self._clock.now()
        captured: list[AlertView] = []

        def work(uow: WorkUnitOfWork) -> None:
            try:
                alert = uow.compliance_alerts.get(EntityId(command.alert_id))
            except ValueError as exc:
                raise InvalidInput("Alerte introuvable.") from exc
            if alert is None:
                raise InvalidInput("Alerte introuvable.")
            before = alert.status.value
            if command.decision == "clear":
                alert.clear(analyst=command.analyst, note=command.note, now=now)
            else:
                alert.escalate(analyst=command.analyst, note=command.note, now=now)
                user = uow.users.get(alert.user_id)
                if user is not None and user.status.value != "FROZEN":
                    user.freeze(f"Escalade AML {alert.kind.value}", now)
                    uow.users.save(user)
            uow.compliance_alerts.save(alert)
            captured.append(AlertView.of(alert))
            self._audit.append(
                actor=command.analyst,
                role=command.role,
                action=f"aml.alert.{command.decision}",
                resource_type="compliance_alert",
                resource_id=command.alert_id,
                before={"status": before},
                after={"status": alert.status.value, "note": command.note.strip() or None},
                now=now,
            )

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


@dataclass(frozen=True, slots=True)
class ExportSuspiciousActivityCommand(Command):
    start: str  # ISO date/datetime inclusif
    end: str  # ISO date/datetime exclusif


@dataclass(frozen=True, slots=True)
class SuspiciousActivityExport:
    content: bytes
    media_type: str
    filename: str


class ExportSuspiciousActivity(
    UseCase[ExportSuspiciousActivityCommand, SuspiciousActivityExport]
):
    """CSV des alertes AML sur la période (déclaration STR/CTR). Colonnes fixes."""

    _COLUMNS = (
        "alert_id",
        "created_at",
        "user_id",
        "kind",
        "status",
        "score",
        "reviewed_by",
        "resolution_note",
        "detail",
    )

    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(
        self, command: ExportSuspiciousActivityCommand
    ) -> SuspiciousActivityExport:
        try:
            start = datetime.fromisoformat(command.start)
            end = datetime.fromisoformat(command.end)
        except ValueError as exc:
            raise InvalidInput("Dates ISO 8601 attendues.") from exc
        if end <= start:
            raise InvalidInput("`end` doit être postérieur à `start`.")

        with self._services.uow() as uow:
            alerts = uow.compliance_alerts.list_between(start.isoformat(), end.isoformat())

        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(self._COLUMNS)
        for a in alerts:
            writer.writerow(
                [
                    str(a.id),
                    a.created_at.isoformat(),
                    str(a.user_id),
                    a.kind.value,
                    a.status.value,
                    a.score,
                    a.reviewed_by or "",
                    a.resolution_note or "",
                    _flatten(a.detail),
                ]
            )
        stamp = start.date().isoformat()
        return SuspiciousActivityExport(
            content=buffer.getvalue().encode("utf-8"),
            media_type="text/csv",
            filename=f"flash-str-{stamp}.csv",
        )


def _flatten(detail: dict[str, Any]) -> str:
    return ";".join(f"{k}={v}" for k, v in sorted(detail.items()))


__all__ = [
    "AlertView",
    "ExportSuspiciousActivity",
    "ExportSuspiciousActivityCommand",
    "ListComplianceAlerts",
    "ListComplianceAlertsCommand",
    "RaiseManualAlert",
    "RaiseManualAlertCommand",
    "ReviewComplianceAlert",
    "ReviewComplianceAlertCommand",
    "SuspiciousActivityExport",
]
