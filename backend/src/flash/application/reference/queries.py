"""Cas d'usage de lecture du référentiel pays / opérateurs (BE-061).

Données publiques et peu volatiles : servies telles quelles depuis la
``ReferenceDirectory`` injectée (statique au bootstrap, SQL + cache Redis en prod).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flash.domain.country.reference import Country, Operator, ReferenceDirectory
from flash.domain.shared.errors import InvalidInput
from flash.domain.shared.identifiers import CountryCode


@dataclass(frozen=True, slots=True)
class OperatorView:
    code: str
    name: str
    msisdn_prefixes: list[str]
    active: bool

    @classmethod
    def of(cls, operator: Operator) -> OperatorView:
        return cls(
            code=operator.code,
            name=operator.name,
            msisdn_prefixes=list(operator.msisdn_prefixes),
            active=operator.active,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "msisdn_prefixes": self.msisdn_prefixes,
            "active": self.active,
        }


@dataclass(frozen=True, slots=True)
class CountryView:
    code: str
    name: str
    currency: str
    dialing_code: str
    timezone: str
    operators: list[OperatorView]

    @classmethod
    def of(cls, country: Country) -> CountryView:
        return cls(
            code=country.code.value,
            name=country.name,
            currency=country.currency.code,
            dialing_code=country.dialing_code,
            timezone=country.timezone,
            operators=[OperatorView.of(o) for o in country.operators],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "code": self.code,
            "name": self.name,
            "currency": self.currency,
            "dialing_code": self.dialing_code,
            "timezone": self.timezone,
            "operators": [o.to_dict() for o in self.operators],
        }


class ListCountries:
    def __init__(self, *, directory: ReferenceDirectory) -> None:
        self._directory = directory

    def execute(self) -> list[CountryView]:
        return [CountryView.of(c) for c in self._directory.countries()]


class GetCountry:
    def __init__(self, *, directory: ReferenceDirectory) -> None:
        self._directory = directory

    def execute(self, code: str) -> CountryView:
        try:
            cc = CountryCode(code.upper())
        except ValueError as exc:
            raise InvalidInput("Code pays invalide.") from exc
        return CountryView.of(self._directory.require_country(cc))


__all__ = ["CountryView", "GetCountry", "ListCountries", "OperatorView"]
