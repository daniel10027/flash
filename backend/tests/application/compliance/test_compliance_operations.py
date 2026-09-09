"""Cas d'usage conformité (BE-076) : file d'alertes, revue, alerte manuelle, export STR."""

from __future__ import annotations

from uuid import UUID

import pytest

from flash.application.compliance.operations import (
    ExportSuspiciousActivity,
    ExportSuspiciousActivityCommand,
    ListComplianceAlerts,
    ListComplianceAlertsCommand,
    RaiseManualAlert,
    RaiseManualAlertCommand,
    ReviewComplianceAlert,
    ReviewComplianceAlertCommand,
)
from flash.application.services import AppServices
from flash.domain.compliance.alert import AlertKind, ComplianceAlert
from flash.domain.identity.pin import Pin
from flash.domain.identity.user import User, UserStatus
from flash.domain.shared.errors import InvalidAccountState, InvalidInput
from flash.domain.shared.identifiers import CountryCode, EntityId, Msisdn
from tests.support.audit import InMemoryAuditLog
from tests.support.fakes import (
    FakePinHasher,
    FixedClock,
    InMemoryIdempotencyStore,
    RecordingEventPublisher,
    SeqIdGenerator,
)
from tests.support.repositories import InMemoryUnitOfWork

CI = CountryCode("CI")
USER_ID = str(UUID(int=1))


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


@pytest.fixture
def audit() -> InMemoryAuditLog:
    return InMemoryAuditLog()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def services(uow: InMemoryUnitOfWork, clock: FixedClock) -> AppServices:
    return AppServices(
        uow=lambda: uow,
        clock=clock,
        ids=SeqIdGenerator(),
        events=RecordingEventPublisher(),
        idempotency=InMemoryIdempotencyStore(),
    )


def _user(uow: InMemoryUnitOfWork) -> User:
    user = User.register(
        user_id=EntityId(USER_ID),
        country=CI,
        msisdn=Msisdn("+2250700000001"),
        pin_hash=FakePinHasher().hash(Pin("1397")),
        now=FixedClock().now(),
    )
    user.activate(FixedClock().now())
    user.pull_events()
    uow.users.add(user)
    return user


def _seed_alert(
    uow: InMemoryUnitOfWork, *, n: int = 1, kind: AlertKind = AlertKind.VELOCITY
) -> EntityId:
    alert = ComplianceAlert.open(
        alert_id=EntityId(str(UUID(int=900 + n))),
        user_id=EntityId(USER_ID),
        kind=kind,
        score=70,
        detail={"count": 22},
        window_key=f"vel:{n}",
        now=FixedClock().now(),
    )
    alert.pull_events()
    uow.compliance_alerts.add(alert)
    return alert.id


class TestListAndManual:
    def test_list_open_and_by_status(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        _seed_alert(uow, n=1)
        rows = ListComplianceAlerts(services=services).execute(
            ListComplianceAlertsCommand()
        )
        assert len(rows) == 1 and rows[0].status == "OPEN"
        assert rows[0].to_dict()["kind"] == "VELOCITY"
        assert (
            ListComplianceAlerts(services=services).execute(
                ListComplianceAlertsCommand(status="CLEARED")
            )
            == []
        )

    def test_list_bad_status_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput, match="Statut"):
            ListComplianceAlerts(services=services).execute(
                ListComplianceAlertsCommand(status="NOPE")
            )

    def test_raise_manual_alert_audits(
        self, services: AppServices, uow: InMemoryUnitOfWork, audit: InMemoryAuditLog
    ) -> None:
        _user(uow)
        view = RaiseManualAlert(
            services=services, audit=audit, clock=FixedClock()
        ).execute(
            RaiseManualAlertCommand(
                user_id=USER_ID, reason="signalement partenaire", analyst="key:compliance",
                role="compliance",
            )
        )
        assert view.kind == "MANUAL" and view.status == "OPEN"
        assert audit.recent()[0].action == "aml.alert.manual"

    def test_manual_alert_guards(
        self, services: AppServices, audit: InMemoryAuditLog
    ) -> None:
        with pytest.raises(InvalidInput, match="motif"):
            RaiseManualAlert(services=services, audit=audit, clock=FixedClock()).execute(
                RaiseManualAlertCommand(
                    user_id=USER_ID, reason=" ", analyst="a", role="compliance"
                )
            )
        with pytest.raises(InvalidInput, match="introuvable"):
            RaiseManualAlert(services=services, audit=audit, clock=FixedClock()).execute(
                RaiseManualAlertCommand(
                    user_id="bad", reason="x", analyst="a", role="compliance"
                )
            )
        with pytest.raises(InvalidInput, match="introuvable"):
            RaiseManualAlert(services=services, audit=audit, clock=FixedClock()).execute(
                RaiseManualAlertCommand(
                    user_id=str(UUID(int=404)), reason="x", analyst="a", role="compliance"
                )
            )


class TestReview:
    def test_clear_marks_cleared_and_audits(
        self, services: AppServices, uow: InMemoryUnitOfWork, audit: InMemoryAuditLog
    ) -> None:
        _user(uow)
        alert_id = _seed_alert(uow)
        view = ReviewComplianceAlert(
            services=services, audit=audit, clock=FixedClock()
        ).execute(
            ReviewComplianceAlertCommand(
                alert_id=str(alert_id), decision="clear", note="RAS",
                analyst="key:compliance", role="compliance",
            )
        )
        assert view.status == "CLEARED"
        assert audit.recent()[0].action == "aml.alert.clear"

    def test_escalate_freezes_the_account(
        self, services: AppServices, uow: InMemoryUnitOfWork, audit: InMemoryAuditLog
    ) -> None:
        _user(uow)
        alert_id = _seed_alert(uow)
        view = ReviewComplianceAlert(
            services=services, audit=audit, clock=FixedClock()
        ).execute(
            ReviewComplianceAlertCommand(
                alert_id=str(alert_id), decision="escalate", note="STR déposée",
                analyst="key:compliance", role="compliance",
            )
        )
        assert view.status == "ESCALATED"
        assert uow.users.get(EntityId(USER_ID)).status is UserStatus.FROZEN  # type: ignore[union-attr]
        assert audit.recent()[0].action == "aml.alert.escalate"

    def test_escalate_when_already_frozen_is_ok(
        self, services: AppServices, uow: InMemoryUnitOfWork, audit: InMemoryAuditLog
    ) -> None:
        user = _user(uow)
        user.freeze("déjà gelé", FixedClock().now())
        user.pull_events()
        uow.users.save(user)
        alert_id = _seed_alert(uow)
        view = ReviewComplianceAlert(
            services=services, audit=audit, clock=FixedClock()
        ).execute(
            ReviewComplianceAlertCommand(
                alert_id=str(alert_id), decision="escalate", note="x",
                analyst="a", role="compliance",
            )
        )
        assert view.status == "ESCALATED"

    def test_review_guards(
        self, services: AppServices, uow: InMemoryUnitOfWork, audit: InMemoryAuditLog
    ) -> None:
        _user(uow)
        alert_id = _seed_alert(uow)
        with pytest.raises(InvalidInput, match="Décision"):
            ReviewComplianceAlert(
                services=services, audit=audit, clock=FixedClock()
            ).execute(
                ReviewComplianceAlertCommand(
                    alert_id=str(alert_id), decision="maybe", note="x",
                    analyst="a", role="compliance",
                )
            )
        with pytest.raises(InvalidInput, match="introuvable"):
            ReviewComplianceAlert(
                services=services, audit=audit, clock=FixedClock()
            ).execute(
                ReviewComplianceAlertCommand(
                    alert_id="bad", decision="clear", note="", analyst="a", role="compliance"
                )
            )
        with pytest.raises(InvalidInput, match="introuvable"):
            ReviewComplianceAlert(
                services=services, audit=audit, clock=FixedClock()
            ).execute(
                ReviewComplianceAlertCommand(
                    alert_id=str(UUID(int=404)), decision="clear", note="",
                    analyst="a", role="compliance",
                )
            )

    def test_cannot_review_twice(
        self, services: AppServices, uow: InMemoryUnitOfWork, audit: InMemoryAuditLog
    ) -> None:
        _user(uow)
        alert_id = _seed_alert(uow)
        cmd = ReviewComplianceAlertCommand(
            alert_id=str(alert_id), decision="clear", note="", analyst="a", role="compliance"
        )
        ReviewComplianceAlert(services=services, audit=audit, clock=FixedClock()).execute(cmd)
        with pytest.raises(InvalidAccountState):
            ReviewComplianceAlert(
                services=services, audit=audit, clock=FixedClock()
            ).execute(cmd)


class TestExport:
    def test_csv_lists_alerts_in_window(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        _seed_alert(uow, n=1, kind=AlertKind.CTR_THRESHOLD)
        _seed_alert(uow, n=2, kind=AlertKind.VELOCITY)
        export = ExportSuspiciousActivity(services=services).execute(
            ExportSuspiciousActivityCommand(
                start="2025-12-01T00:00:00+00:00", end="2026-12-01T00:00:00+00:00"
            )
        )
        assert export.media_type == "text/csv"
        text = export.content.decode()
        assert text.splitlines()[0].startswith("alert_id,created_at,user_id,kind")
        assert "CTR_THRESHOLD" in text and "VELOCITY" in text

    def test_window_excludes_outside(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        _seed_alert(uow, n=1)
        export = ExportSuspiciousActivity(services=services).execute(
            ExportSuspiciousActivityCommand(
                start="2020-01-01T00:00:00+00:00", end="2020-02-01T00:00:00+00:00"
            )
        )
        assert export.content.decode().strip().count("\n") == 0  # en-tête seule

    def test_bad_dates_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput, match="ISO 8601"):
            ExportSuspiciousActivity(services=services).execute(
                ExportSuspiciousActivityCommand(start="hier", end="aujourd'hui")
            )
        with pytest.raises(InvalidInput, match="postérieur"):
            ExportSuspiciousActivity(services=services).execute(
                ExportSuspiciousActivityCommand(
                    start="2026-02-01T00:00:00+00:00", end="2026-01-01T00:00:00+00:00"
                )
            )
