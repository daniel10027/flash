"""Tests du registre d'audit consultable (BE-078) : filtres + contrôle d'intégrité."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

import pytest

from flash.application.audit.registry import (
    QueryAuditLog,
    QueryAuditLogCommand,
    VerifyAuditChain,
    VerifyAuditChainCommand,
)
from flash.domain.shared.errors import InvalidInput
from tests.support.audit import InMemoryAuditLog

T0 = datetime(2026, 3, 1, 12, 0, tzinfo=UTC)


@pytest.fixture
def audit() -> InMemoryAuditLog:
    log = InMemoryAuditLog()
    log.append(
        actor="key:admin", role="admin", action="country.create",
        resource_type="country", resource_id="CI", before=None, after={"n": 1},
        now=T0,
    )
    log.append(
        actor="key:compliance", role="compliance", action="account.freeze",
        resource_type="account", resource_id="acc-1", before={"f": False},
        after={"f": True}, now=T0.replace(hour=13),
    )
    log.append(
        actor="key:admin", role="admin", action="account.freeze",
        resource_type="account", resource_id="acc-2", before={"f": False},
        after={"f": True}, now=T0.replace(day=5),
    )
    return log


class TestQueryAuditLog:
    def test_no_filter_returns_all_newest_first(self, audit: InMemoryAuditLog) -> None:
        page = QueryAuditLog(audit=audit).execute(QueryAuditLogCommand())
        assert [e.sequence for e in page.entries] == [3, 2, 1]
        assert page.chain is None
        assert "chain" not in page.to_dict()

    def test_filter_by_actor(self, audit: InMemoryAuditLog) -> None:
        page = QueryAuditLog(audit=audit).execute(
            QueryAuditLogCommand(actor="key:admin")
        )
        assert [e.sequence for e in page.entries] == [3, 1]

    def test_filter_by_action_and_resource_type(self, audit: InMemoryAuditLog) -> None:
        page = QueryAuditLog(audit=audit).execute(
            QueryAuditLogCommand(action="account.freeze", resource_type="account")
        )
        assert [e.resource_id for e in page.entries] == ["acc-2", "acc-1"]

    def test_filter_by_resource_id(self, audit: InMemoryAuditLog) -> None:
        page = QueryAuditLog(audit=audit).execute(
            QueryAuditLogCommand(resource_id="acc-1")
        )
        assert [e.sequence for e in page.entries] == [2]

    def test_filter_by_period_half_open(self, audit: InMemoryAuditLog) -> None:
        page = QueryAuditLog(audit=audit).execute(
            QueryAuditLogCommand(
                start="2026-03-01T00:00:00+00:00", end="2026-03-02T00:00:00+00:00"
            )
        )
        assert [e.sequence for e in page.entries] == [2, 1]  # le 5 mars est exclu

    def test_naive_dates_treated_as_utc(self, audit: InMemoryAuditLog) -> None:
        page = QueryAuditLog(audit=audit).execute(
            QueryAuditLogCommand(start="2026-03-04T00:00:00")
        )
        assert [e.sequence for e in page.entries] == [3]

    def test_cursor_and_limit(self, audit: InMemoryAuditLog) -> None:
        page = QueryAuditLog(audit=audit).execute(
            QueryAuditLogCommand(limit=1, before_sequence=3)
        )
        assert [e.sequence for e in page.entries] == [2]

    def test_verify_flag_attaches_chain_report(self, audit: InMemoryAuditLog) -> None:
        page = QueryAuditLog(audit=audit).execute(QueryAuditLogCommand(verify=True))
        assert page.chain is not None and page.chain.intact is True
        payload = page.to_dict()
        assert payload["chain"]["checked"] == 3
        assert payload["intact"] is True

    def test_bad_date_rejected(self, audit: InMemoryAuditLog) -> None:
        with pytest.raises(InvalidInput, match="ISO 8601"):
            QueryAuditLog(audit=audit).execute(QueryAuditLogCommand(start="hier"))

    def test_end_before_start_rejected(self, audit: InMemoryAuditLog) -> None:
        with pytest.raises(InvalidInput, match="postérieur"):
            QueryAuditLog(audit=audit).execute(
                QueryAuditLogCommand(
                    start="2026-03-05T00:00:00+00:00", end="2026-03-01T00:00:00+00:00"
                )
            )


class TestVerifyAuditChain:
    def test_intact_chain(self, audit: InMemoryAuditLog) -> None:
        report = VerifyAuditChain(audit=audit).execute(VerifyAuditChainCommand())
        assert report.intact is True and report.broken_at is None

    def test_detects_tampering_and_locates_it(self, audit: InMemoryAuditLog) -> None:
        audit._entries[1] = replace(audit._entries[1], after={"f": "pirate"})
        report = VerifyAuditChain(audit=audit).execute(VerifyAuditChainCommand())
        assert report.intact is False
        assert report.broken_at == 2
