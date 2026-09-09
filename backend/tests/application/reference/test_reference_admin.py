"""Tests du CRUD back-office du référentiel + traçabilité (BE-062)."""

from __future__ import annotations

import pytest

from flash.application.reference.admin import (
    DeleteCountry,
    DeleteCountryCommand,
    DeleteOperator,
    DeleteOperatorCommand,
    ListAuditEntries,
    ListAuditEntriesCommand,
    UpsertCountry,
    UpsertCountryCommand,
    UpsertOperator,
    UpsertOperatorCommand,
)
from flash.domain.shared.errors import InvalidInput
from flash.domain.shared.identifiers import CountryCode
from flash.infrastructure.reference import MutableReferenceDirectory
from tests.support.audit import InMemoryAuditLog
from tests.support.fakes import FixedClock


@pytest.fixture
def editor() -> MutableReferenceDirectory:
    return MutableReferenceDirectory()


@pytest.fixture
def audit() -> InMemoryAuditLog:
    return InMemoryAuditLog()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


def _upsert_country(editor: MutableReferenceDirectory, audit: InMemoryAuditLog, clock: FixedClock):
    return UpsertCountry(editor=editor, audit=audit, clock=clock)


class TestCountryCrud:
    def test_create_then_update_traces_before_after(
        self, editor: MutableReferenceDirectory, audit: InMemoryAuditLog, clock: FixedClock
    ) -> None:
        uc = _upsert_country(editor, audit, clock)
        uc.execute(
            UpsertCountryCommand(
                actor="key:compliance",
                role="compliance",
                code="ZA",
                name="Afrique du Sud",
                currency="XOF",
                dialing_code="27",
            )
        )
        view = uc.execute(
            UpsertCountryCommand(
                actor="key:compliance",
                role="compliance",
                code="ZA",
                name="RSA",
                currency="XOF",
                dialing_code="27",
                active=False,
            )
        )
        assert view.name == "RSA"
        assert editor.country(CountryCode("ZA")).active is False  # type: ignore[union-attr]

        entries = audit.recent()
        assert [e.action for e in entries] == ["country.update", "country.create"]
        upd = entries[0]
        assert upd.before == {
            "code": "ZA",
            "name": "Afrique du Sud",
            "currency": "XOF",
            "dialing_code": "27",
            "timezone": "UTC",
            "active": True,
        }
        assert upd.after["name"] == "RSA" and upd.after["active"] is False
        assert audit.verify() is True

    def test_update_preserves_existing_operators(
        self, editor: MutableReferenceDirectory, audit: InMemoryAuditLog, clock: FixedClock
    ) -> None:
        before = editor.country(CountryCode("CI")).operators  # type: ignore[union-attr]
        _upsert_country(editor, audit, clock).execute(
            UpsertCountryCommand(
                actor="a", role="admin", code="CI", name="CIV", currency="XOF", dialing_code="225"
            )
        )
        assert editor.country(CountryCode("CI")).operators == before  # type: ignore[union-attr]

    def test_unknown_currency_rejected(
        self, editor: MutableReferenceDirectory, audit: InMemoryAuditLog, clock: FixedClock
    ) -> None:
        with pytest.raises(InvalidInput):
            _upsert_country(editor, audit, clock).execute(
                UpsertCountryCommand(
                    actor="a", role="admin", code="CI", name="X", currency="ZZZ", dialing_code="225"
                )
            )

    def test_bad_code_rejected(
        self, editor: MutableReferenceDirectory, audit: InMemoryAuditLog, clock: FixedClock
    ) -> None:
        with pytest.raises(InvalidInput, match="Code pays"):
            _upsert_country(editor, audit, clock).execute(
                UpsertCountryCommand(
                    actor="a", role="admin", code="CIV", name="X", currency="XOF", dialing_code="1"
                )
            )

    def test_bad_dialing_code_rejected(
        self, editor: MutableReferenceDirectory, audit: InMemoryAuditLog, clock: FixedClock
    ) -> None:
        with pytest.raises(InvalidInput):
            _upsert_country(editor, audit, clock).execute(
                UpsertCountryCommand(
                    actor="a", role="admin", code="CI", name="X", currency="XOF", dialing_code="ab"
                )
            )

    def test_delete_traces_and_removes(
        self, editor: MutableReferenceDirectory, audit: InMemoryAuditLog, clock: FixedClock
    ) -> None:
        DeleteCountry(editor=editor, audit=audit, clock=clock).execute(
            DeleteCountryCommand(actor="key:admin", role="admin", code="ga")
        )
        assert editor.country(CountryCode("GA")) is None
        [entry] = audit.recent()
        assert entry.action == "country.delete" and entry.after is None
        assert entry.before["code"] == "GA"

    def test_delete_unknown_rejected(
        self, editor: MutableReferenceDirectory, audit: InMemoryAuditLog, clock: FixedClock
    ) -> None:
        with pytest.raises(InvalidInput, match="introuvable"):
            DeleteCountry(editor=editor, audit=audit, clock=clock).execute(
                DeleteCountryCommand(actor="a", role="admin", code="ZZ")
            )


class TestOperatorCrud:
    def test_upsert_then_delete_operator(
        self, editor: MutableReferenceDirectory, audit: InMemoryAuditLog, clock: FixedClock
    ) -> None:
        view = UpsertOperator(editor=editor, audit=audit, clock=clock).execute(
            UpsertOperatorCommand(
                actor="key:compliance",
                role="compliance",
                country="CI",
                code="TELECEL_CI",
                name="Telecel Money",
                msisdn_prefixes=["09"],
            )
        )
        assert view.code == "TELECEL_CI"
        assert editor.operator("TELECEL_CI") is not None

        DeleteOperator(editor=editor, audit=audit, clock=clock).execute(
            DeleteOperatorCommand(actor="key:compliance", role="compliance", code="TELECEL_CI")
        )
        assert editor.operator("TELECEL_CI") is None
        assert [e.action for e in audit.recent()] == ["operator.delete", "operator.create"]
        assert audit.verify() is True

    def test_upsert_operator_unknown_country_rejected(
        self, editor: MutableReferenceDirectory, audit: InMemoryAuditLog, clock: FixedClock
    ) -> None:
        with pytest.raises(InvalidInput, match="Pays inconnu"):
            UpsertOperator(editor=editor, audit=audit, clock=clock).execute(
                UpsertOperatorCommand(
                    actor="a", role="admin", country="ZZ", code="X", name="X"
                )
            )

    def test_upsert_operator_blank_code_rejected(
        self, editor: MutableReferenceDirectory, audit: InMemoryAuditLog, clock: FixedClock
    ) -> None:
        with pytest.raises(InvalidInput):
            UpsertOperator(editor=editor, audit=audit, clock=clock).execute(
                UpsertOperatorCommand(actor="a", role="admin", country="CI", code=" ", name="X")
            )

    def test_delete_unknown_operator_rejected(
        self, editor: MutableReferenceDirectory, audit: InMemoryAuditLog, clock: FixedClock
    ) -> None:
        with pytest.raises(InvalidInput, match="introuvable"):
            DeleteOperator(editor=editor, audit=audit, clock=clock).execute(
                DeleteOperatorCommand(actor="a", role="admin", code="NOPE")
            )


def test_list_audit_entries_paginates(
    editor: MutableReferenceDirectory, audit: InMemoryAuditLog, clock: FixedClock
) -> None:
    for code in ("AA", "BB", "CC"):
        _upsert_country(editor, audit, clock).execute(
            UpsertCountryCommand(
                actor="a", role="admin", code="C" + code[0], name=code, currency="XOF",
                dialing_code="10",
            )
        )
    page = ListAuditEntries(audit=audit).execute(ListAuditEntriesCommand(limit=2))
    assert [e.sequence for e in page] == [3, 2]
    older = ListAuditEntries(audit=audit).execute(
        ListAuditEntriesCommand(limit=5, before_sequence=2)
    )
    assert [e.sequence for e in older] == [1]
