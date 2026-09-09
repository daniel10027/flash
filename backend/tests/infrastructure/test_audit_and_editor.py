"""Intégration : ``SqlAlchemyAuditLog`` + ``SqlAlchemyReferenceEditor`` (BE-062)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session, sessionmaker

from flash.domain.country.reference import Country, Operator
from flash.domain.shared.identifiers import CountryCode
from flash.domain.shared.money import Currency
from flash.infrastructure.db.audit_log import SqlAlchemyAuditLog
from flash.infrastructure.ids import Uuid7Generator
from flash.infrastructure.reference import (
    SqlAlchemyReferenceDirectory,
    SqlAlchemyReferenceEditor,
    seed_reference,
)

pytestmark = pytest.mark.integration

T0 = datetime(2026, 1, 1, tzinfo=UTC)
XOF = Currency.of("XOF")


def test_audit_log_chains_and_verifies(session_factory: sessionmaker[Session]) -> None:
    log = SqlAlchemyAuditLog(session_factory, Uuid7Generator())
    first = log.append(
        actor="key:admin",
        role="admin",
        action="country.create",
        resource_type="country",
        resource_id="ZA",
        before=None,
        after={"name": "Afrique du Sud"},
        now=T0,
    )
    second = log.append(
        actor="key:compliance",
        role="compliance",
        action="country.update",
        resource_type="country",
        resource_id="ZA",
        before={"name": "Afrique du Sud"},
        after={"name": "RSA"},
        now=T0,
    )
    assert first.sequence == 1 and first.prev_hash == "0" * 64
    assert second.sequence == 2 and second.prev_hash == first.entry_hash
    assert log.verify() is True

    recent = log.recent(limit=1)
    assert [e.sequence for e in recent] == [2]
    assert log.recent(before_sequence=2)[0].sequence == 1


def test_sql_editor_writes_and_reads_back(session_factory: sessionmaker[Session]) -> None:
    seed_reference(session_factory)
    bumped: list[int] = []
    editor = SqlAlchemyReferenceEditor(session_factory, on_change=lambda: bumped.append(1))

    editor.save_country(
        Country(
            code=CountryCode("KE"),
            name="Kenya",
            currency=XOF,
            dialing_code="254",
            timezone="Africa/Nairobi",
        )
    )
    editor.save_operator(
        Operator(code="MPESA_KE", name="M-Pesa", country=CountryCode("KE"), msisdn_prefixes=("7",))
    )
    assert len(bumped) == 2

    directory = SqlAlchemyReferenceDirectory(session_factory)
    ke = directory.require_country(CountryCode("KE"))
    assert ke.currency == XOF
    assert {o.code for o in ke.operators} == {"MPESA_KE"}

    assert editor.country(CountryCode("KE")) is not None
    assert editor.operator("MPESA_KE") is not None

    editor.remove_operator("MPESA_KE")
    editor.remove_country(CountryCode("KE"))
    assert SqlAlchemyReferenceDirectory(session_factory).country(CountryCode("KE")) is None
