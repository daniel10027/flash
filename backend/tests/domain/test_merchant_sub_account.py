"""Tests de l'agrégat ``MerchantSubAccount`` — caisses / employés (reste de BE-068)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from flash.domain.merchants.sub_account import MerchantSubAccount, SubAccountKind
from flash.domain.shared.errors import InvalidInput
from flash.domain.shared.identifiers import EntityId

T0 = datetime(2026, 1, 1, tzinfo=UTC)
SID = EntityId(str(UUID(int=1)))
MID = EntityId(str(UUID(int=2)))


def _open(**kw: object) -> MerchantSubAccount:
    params: dict[str, object] = {
        "sub_account_id": SID,
        "merchant_id": MID,
        "kind": SubAccountKind.TILL,
        "label": "Caisse 1",
        "now": T0,
    }
    params.update(kw)
    return MerchantSubAccount.open(**params)  # type: ignore[arg-type]


def test_open_records_event_and_trims_label() -> None:
    sub = _open(label="  Caisse principale  ", external_ref="  T-01 ")
    assert sub.label == "Caisse principale"
    assert sub.external_ref == "T-01"
    assert sub.active is True
    assert [e.name for e in sub.pull_events()] == ["MerchantSubAccountOpened"]


def test_open_requires_label() -> None:
    with pytest.raises(InvalidInput, match="libellé est requis"):
        _open(label="   ")


def test_open_rejects_overlong_label() -> None:
    with pytest.raises(InvalidInput, match="trop long"):
        _open(label="x" * 61)


def test_open_rejects_overlong_external_ref() -> None:
    with pytest.raises(InvalidInput, match="Référence externe trop longue"):
        _open(external_ref="x" * 41)


def test_update_rejects_overlong_fields() -> None:
    sub = _open()
    with pytest.raises(InvalidInput, match="Libellé trop long"):
        sub.update(now=T0, label="x" * 61)
    with pytest.raises(InvalidInput, match="Référence externe trop longue"):
        sub.update(now=T0, external_ref="y" * 41)


def test_repr_is_readable() -> None:
    assert "Caisse 1" in repr(_open())


def test_update_label_and_deactivate() -> None:
    sub = _open()
    sub.pull_events()
    sub.update(now=T0, label="Caisse 2", active=False)
    assert sub.label == "Caisse 2" and sub.active is False
    assert [e.name for e in sub.pull_events()] == ["MerchantSubAccountUpdated"]


def test_update_blank_label_rejected() -> None:
    sub = _open()
    with pytest.raises(InvalidInput, match="ne peut pas être vide"):
        sub.update(now=T0, label="  ")


def test_update_clears_external_ref_with_empty_string() -> None:
    sub = _open(external_ref="T-01")
    sub.update(now=T0, external_ref="")
    assert sub.external_ref is None


def test_ensure_usable_rejects_inactive() -> None:
    sub = _open()
    sub.update(now=T0, active=False)
    with pytest.raises(InvalidInput, match="désactivé"):
        sub.ensure_usable()
    sub.update(now=T0, active=True)
    sub.ensure_usable()  # ne lève pas
