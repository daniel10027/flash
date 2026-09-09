"""Tests de ``AuditEntry`` : hachage canonique + intégrité de la chaîne (BE-062/078)."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime

from flash.domain.audit.entry import (
    GENESIS_HASH,
    AuditEntry,
    audit_chain_report,
    compute_entry_hash,
    verify_chain,
)

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _entry(seq: int, prev: str, *, after: dict | None = None) -> AuditEntry:
    return AuditEntry.create(
        id=f"a-{seq}",
        sequence=seq,
        actor="key:admin",
        role="admin",
        action="country.update",
        resource_type="country",
        resource_id="CI",
        before={"name": "Côte d'Ivoire"},
        after=after if after is not None else {"name": "CI"},
        occurred_at=T0,
        prev_hash=prev,
    )


def test_create_computes_deterministic_hash() -> None:
    a = _entry(1, GENESIS_HASH)
    b = _entry(1, GENESIS_HASH)
    assert a.entry_hash == b.entry_hash
    assert a.entry_hash == compute_entry_hash(
        sequence=1,
        actor="key:admin",
        role="admin",
        action="country.update",
        resource_type="country",
        resource_id="CI",
        before={"name": "Côte d'Ivoire"},
        after={"name": "CI"},
        occurred_at=T0,
        prev_hash=GENESIS_HASH,
    )


def test_hash_changes_with_payload() -> None:
    assert _entry(1, GENESIS_HASH).entry_hash != _entry(
        1, GENESIS_HASH, after={"name": "autre"}
    ).entry_hash


def test_is_intact_detects_tampering() -> None:
    entry = _entry(1, GENESIS_HASH)
    assert entry.is_intact
    tampered = replace(entry, after={"name": "pirate"})
    assert not tampered.is_intact


def test_verify_chain_happy_path() -> None:
    e1 = _entry(1, GENESIS_HASH)
    e2 = _entry(2, e1.entry_hash)
    e3 = _entry(3, e2.entry_hash)
    assert verify_chain([e1, e2, e3]) is True
    assert verify_chain([]) is True


def test_verify_chain_rejects_gap_and_broken_link_and_tamper() -> None:
    e1 = _entry(1, GENESIS_HASH)
    e2 = _entry(2, e1.entry_hash)
    assert verify_chain([e1, _entry(3, e1.entry_hash)]) is False  # trou de séquence
    assert verify_chain([e1, _entry(2, "deadbeef")]) is False  # prev_hash cassé
    assert verify_chain([e1, replace(e2, after={"x": 1})]) is False  # ligne altérée


def test_chain_report_happy_path_counts_entries() -> None:
    e1 = _entry(1, GENESIS_HASH)
    e2 = _entry(2, e1.entry_hash)
    report = audit_chain_report([e1, e2])
    assert report.intact is True
    assert report.checked == 2
    assert report.broken_at is None and report.reason is None
    assert audit_chain_report([]).to_dict() == {
        "intact": True,
        "checked": 0,
        "broken_at": None,
        "reason": None,
    }


def test_chain_report_localises_sequence_gap() -> None:
    e1 = _entry(1, GENESIS_HASH)
    report = audit_chain_report([e1, _entry(3, e1.entry_hash)])
    assert report.intact is False
    assert report.broken_at == 3
    assert report.checked == 2
    assert report.reason is not None and "séquence" in report.reason


def test_chain_report_localises_broken_prev_hash() -> None:
    e1 = _entry(1, GENESIS_HASH)
    report = audit_chain_report([e1, _entry(2, "deadbeef")])
    assert report.intact is False
    assert report.broken_at == 2
    assert report.reason is not None and "prev_hash" in report.reason


def test_chain_report_localises_tampered_content() -> None:
    e1 = _entry(1, GENESIS_HASH)
    e2 = _entry(2, e1.entry_hash)
    report = audit_chain_report([e1, replace(e2, after={"x": 1})])
    assert report.intact is False
    assert report.broken_at == 2
    assert report.reason is not None and "altér" in report.reason


def test_to_dict_roundtrips_fields() -> None:
    payload = _entry(1, GENESIS_HASH).to_dict()
    assert payload["sequence"] == 1
    assert payload["before"] == {"name": "Côte d'Ivoire"}
    assert payload["prev_hash"] == GENESIS_HASH
    assert len(payload["entry_hash"]) == 64


def test_none_before_after_serialise() -> None:
    entry = AuditEntry.create(
        id="a-9",
        sequence=1,
        actor="key:compliance",
        role="compliance",
        action="country.create",
        resource_type="country",
        resource_id="ML",
        before=None,
        after={"name": "Mali"},
        occurred_at=T0,
        prev_hash=GENESIS_HASH,
    )
    assert entry.to_dict()["before"] is None
    assert entry.is_intact
