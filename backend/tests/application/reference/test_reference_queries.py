"""Tests des lectures du référentiel (BE-061)."""

from __future__ import annotations

import pytest

from flash.application.reference.queries import GetCountry, ListCountries
from flash.domain.country.directory import UnsupportedCountry
from flash.domain.shared.errors import InvalidInput
from flash.infrastructure.reference import StaticReferenceDirectory


@pytest.fixture
def directory() -> StaticReferenceDirectory:
    return StaticReferenceDirectory()


def test_list_countries_returns_active_set(directory: StaticReferenceDirectory) -> None:
    views = ListCountries(directory=directory).execute()
    codes = {v.code for v in views}
    assert {"CI", "SN", "CM", "GA"} <= codes
    ci = next(v for v in views if v.code == "CI")
    assert ci.currency == "XOF" and ci.dialing_code == "225"
    assert any(o.code == "ORANGE_CI" for o in ci.operators)
    cm = next(v for v in views if v.code == "CM")
    assert cm.currency == "XAF"


def test_country_view_to_dict(directory: StaticReferenceDirectory) -> None:
    payload = GetCountry(directory=directory).execute("ci").to_dict()
    assert payload["code"] == "CI"
    assert payload["operators"][0]["msisdn_prefixes"]  # liste non vide pour Orange


def test_get_country_is_case_insensitive(directory: StaticReferenceDirectory) -> None:
    assert GetCountry(directory=directory).execute("Sn").code == "SN"


def test_get_country_unknown_raises(directory: StaticReferenceDirectory) -> None:
    with pytest.raises(UnsupportedCountry):
        GetCountry(directory=directory).execute("US")


def test_get_country_malformed_raises(directory: StaticReferenceDirectory) -> None:
    with pytest.raises(InvalidInput, match="Code pays"):
        GetCountry(directory=directory).execute("XYZ")
