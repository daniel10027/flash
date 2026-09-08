"""Association pays → devise et port ``CountryDirectory``.

Table statique pour le lancement (UEMOA / XOF, CEMAC / XAF). Le référentiel complet
(opérateurs, fuseaux, fenêtres) arrive avec ``BE-061`` et implémentera le même port.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from flash.domain.shared.errors import DomainError
from flash.domain.shared.identifiers import CountryCode
from flash.domain.shared.money import Currency

_CURRENCY_BY_COUNTRY: dict[str, str] = {
    # UEMOA — Franc CFA BCEAO
    "CI": "XOF",
    "SN": "XOF",
    "ML": "XOF",
    "BF": "XOF",
    "BJ": "XOF",
    "TG": "XOF",
    "NE": "XOF",
    "GW": "XOF",
    # CEMAC — Franc CFA BEAC
    "CM": "XAF",
    "GA": "XAF",
}


class UnsupportedCountry(DomainError):
    code = "UNSUPPORTED_COUNTRY"
    message = "Ce pays n'est pas encore pris en charge."


@runtime_checkable
class CountryDirectory(Protocol):
    def is_supported(self, country: CountryCode) -> bool: ...

    def currency_for(self, country: CountryCode) -> Currency: ...


class StaticCountryDirectory:
    def is_supported(self, country: CountryCode) -> bool:
        return country.value in _CURRENCY_BY_COUNTRY

    def currency_for(self, country: CountryCode) -> Currency:
        try:
            return Currency.of(_CURRENCY_BY_COUNTRY[country.value])
        except KeyError:
            raise UnsupportedCountry(country=country.value) from None


__all__ = ["CountryDirectory", "StaticCountryDirectory", "UnsupportedCountry"]
