"""Tests du référentiel pays / opérateurs (BE-061) : VOs + logique de la ``ReferenceDirectory``."""

from __future__ import annotations

import pytest

from flash.domain.country.directory import UnsupportedCountry
from flash.domain.country.reference import Country, Operator, _DirectoryMixin
from flash.domain.shared.identifiers import CountryCode, Msisdn
from flash.domain.shared.money import Currency

XOF = Currency.of("XOF")
CI = CountryCode("CI")
SN = CountryCode("SN")


def _op(
    country: str, code: str, prefixes: tuple[str, ...] = (), *, active: bool = True
) -> Operator:
    return Operator(
        code=code,
        name=f"{code} Money",
        country=CountryCode(country),
        msisdn_prefixes=prefixes,
        active=active,
    )


def _country(
    code: str, *, dialing: str, operators: tuple[Operator, ...] = (), active: bool = True
) -> Country:
    return Country(
        code=CountryCode(code),
        name=code,
        currency=XOF,
        dialing_code=dialing,
        operators=operators,
        active=active,
    )


class _Dir(_DirectoryMixin):
    def __init__(self, rows: tuple[Country, ...]) -> None:
        self._rows = rows

    def _all(self) -> tuple[Country, ...]:
        return self._rows


class TestValueObjects:
    def test_operator_requires_code_and_name(self) -> None:
        with pytest.raises(ValueError, match="code"):
            Operator(code="  ", name="X", country=CI)
        with pytest.raises(ValueError, match="nom"):
            Operator(code="X", name=" ", country=CI)

    def test_operator_rejects_non_digit_prefix(self) -> None:
        with pytest.raises(ValueError, match="Préfixe"):
            _op("CI", "ORANGE", ("07a",))

    def test_operator_handles_national_prefix(self) -> None:
        orange = _op("CI", "ORANGE_CI", ("07", "27"))
        assert orange.handles(Msisdn("+2250712345678"), dialing_code="225") is True
        assert orange.handles(Msisdn("+2250512345678"), dialing_code="225") is False
        # autre indicatif national
        assert orange.handles(Msisdn("+2210712345678"), dialing_code="225") is False

    def test_country_requires_name_and_numeric_dialing(self) -> None:
        with pytest.raises(ValueError, match="nom du pays"):
            Country(code=CI, name=" ", currency=XOF, dialing_code="225")
        with pytest.raises(ValueError, match="indicatif"):
            Country(code=CI, name="CI", currency=XOF, dialing_code="22X")

    def test_country_rejects_foreign_operator(self) -> None:
        with pytest.raises(ValueError, match="n'appartient pas"):
            _country("CI", dialing="225", operators=(_op("SN", "ORANGE_SN"),))

    def test_country_operator_for(self) -> None:
        c = _country(
            "CI",
            dialing="225",
            operators=(_op("CI", "ORANGE_CI", ("07",)), _op("CI", "MTN_CI", ("05",))),
        )
        assert c.operator_for(Msisdn("+2250712345678")).code == "ORANGE_CI"  # type: ignore[union-attr]
        assert c.operator_for(Msisdn("+2250912345678")) is None

    def test_country_operator_for_skips_inactive(self) -> None:
        c = _country("CI", dialing="225", operators=(_op("CI", "OLD", ("07",), active=False),))
        assert c.operator_for(Msisdn("+2250712345678")) is None


class TestDirectoryMixin:
    def _dir(self) -> _Dir:
        return _Dir(
            (
                _country("CI", dialing="225", operators=(_op("CI", "ORANGE_CI", ("07",)),)),
                _country("SN", dialing="221"),
                _country("XX", dialing="999", active=False),
            )
        )

    def test_countries_excludes_inactive_by_default(self) -> None:
        d = self._dir()
        assert [c.code.value for c in d.countries()] == ["CI", "SN"]
        assert [c.code.value for c in d.countries(include_inactive=True)] == ["CI", "SN", "XX"]

    def test_country_lookup(self) -> None:
        d = self._dir()
        assert d.country(CI) is not None
        assert d.country(CountryCode("ML")) is None

    def test_require_country_raises_for_unknown_or_inactive(self) -> None:
        d = self._dir()
        assert d.require_country(CI).code == CI
        with pytest.raises(UnsupportedCountry):
            d.require_country(CountryCode("ML"))
        with pytest.raises(UnsupportedCountry):
            d.require_country(CountryCode("XX"))

    def test_operators_and_operator_for_msisdn(self) -> None:
        d = self._dir()
        assert [o.code for o in d.operators(CI)] == ["ORANGE_CI"]
        assert d.operators(CountryCode("ML")) == ()
        assert d.operator_for_msisdn(Msisdn("+2250712345678")).code == "ORANGE_CI"  # type: ignore[union-attr]
        assert d.operator_for_msisdn(Msisdn("+2250912345678")) is None
        assert d.operator_for_msisdn(Msisdn("+2210712345678")) is None  # SN, pas d'opérateurs

    def test_operator_for_msisdn_unknown_dialing(self) -> None:
        d = self._dir()
        assert d.operator_for_msisdn(Msisdn("+15551234567")) is None  # indicatif inconnu

    def test_country_directory_compat(self) -> None:
        d = self._dir()
        assert d.is_supported(CI) is True
        assert d.is_supported(CountryCode("XX")) is False
        assert d.currency_for(CI) == XOF
        with pytest.raises(UnsupportedCountry):
            d.currency_for(CountryCode("ML"))
