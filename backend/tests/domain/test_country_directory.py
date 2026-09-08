"""Tests du référentiel pays statique (support de BE-025 ; remplacé par BE-061)."""

from __future__ import annotations

import pytest

from flash.domain.country.directory import StaticCountryDirectory, UnsupportedCountry
from flash.domain.shared.identifiers import CountryCode
from flash.domain.shared.money import Currency


class TestStaticCountryDirectory:
    def setup_method(self) -> None:
        self.directory = StaticCountryDirectory()

    @pytest.mark.parametrize(
        "code,currency",
        [("CI", "XOF"), ("SN", "XOF"), ("BF", "XOF"), ("CM", "XAF"), ("GA", "XAF")],
    )
    def test_currency_for_supported_country(self, code: str, currency: str) -> None:
        assert self.directory.currency_for(CountryCode(code)) == Currency.of(currency)

    def test_is_supported(self) -> None:
        assert self.directory.is_supported(CountryCode("CI")) is True
        assert self.directory.is_supported(CountryCode("US")) is False

    def test_unsupported_country_raises(self) -> None:
        with pytest.raises(UnsupportedCountry) as exc:
            self.directory.currency_for(CountryCode("US"))
        assert exc.value.code == "UNSUPPORTED_COUNTRY"
        assert exc.value.details == {"country": "US"}
