"""Référentiel pays & opérateurs (BE-061).

``Country`` et ``Operator`` sont des *value objects* immuables. Le port
``ReferenceDirectory`` expose une vue **cohérente** de ce référentiel ; ses
implémentations (statique pour le bootstrap, SQL + cache Redis en production) vivent
dans ``infrastructure``. Le contrat inclut ``is_supported`` / ``currency_for`` : une
``ReferenceDirectory`` satisfait donc aussi l'ancien port ``CountryDirectory``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

from flash.domain.country.directory import UnsupportedCountry
from flash.domain.shared.identifiers import CountryCode, Msisdn
from flash.domain.shared.money import Currency


@dataclass(frozen=True, slots=True)
class Operator:
    """Un opérateur mobile money d'un pays (Orange, MTN, Moov, Wave…)."""

    code: str
    name: str
    country: CountryCode
    msisdn_prefixes: tuple[str, ...] = ()
    active: bool = True

    def __post_init__(self) -> None:
        if not self.code.strip():
            raise ValueError("Le code opérateur est requis.")
        if not self.name.strip():
            raise ValueError("Le nom opérateur est requis.")
        for prefix in self.msisdn_prefixes:
            if not prefix.isdigit():
                raise ValueError(f"Préfixe MSISDN invalide : {prefix!r} (chiffres attendus).")

    def handles(self, msisdn: Msisdn, *, dialing_code: str) -> bool:
        """Vrai si le numéro national (indicatif retiré) commence par un préfixe connu."""
        digits = msisdn.value[1:]
        if not digits.startswith(dialing_code):
            return False
        national = digits[len(dialing_code) :]
        return any(national.startswith(p) for p in self.msisdn_prefixes)


@dataclass(frozen=True, slots=True)
class Country:
    code: CountryCode
    name: str
    currency: Currency
    dialing_code: str
    timezone: str = "UTC"
    active: bool = True
    operators: tuple[Operator, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("Le nom du pays est requis.")
        if not self.dialing_code.isdigit():
            raise ValueError("L'indicatif téléphonique doit être numérique.")
        for operator in self.operators:
            if operator.country != self.code:
                raise ValueError(
                    f"L'opérateur {operator.code} n'appartient pas au pays {self.code}."
                )

    def operator_for(self, msisdn: Msisdn) -> Operator | None:
        for operator in self.operators:
            if operator.active and operator.handles(msisdn, dialing_code=self.dialing_code):
                return operator
        return None


@runtime_checkable
class ReferenceDirectory(Protocol):
    def countries(self, *, include_inactive: bool = False) -> tuple[Country, ...]: ...

    def country(self, code: CountryCode) -> Country | None: ...

    def require_country(self, code: CountryCode) -> Country: ...

    def operators(self, code: CountryCode) -> tuple[Operator, ...]: ...

    def operator_for_msisdn(self, msisdn: Msisdn) -> Operator | None: ...

    # --- compatibilité avec l'ancien port CountryDirectory
    def is_supported(self, country: CountryCode) -> bool: ...

    def currency_for(self, country: CountryCode) -> Currency: ...


class _DirectoryMixin:
    """Logique commune : dérive tout des ``Country`` retournés par ``_all()``."""

    def _all(self) -> tuple[Country, ...]:  # pragma: no cover - fourni par les sous-classes
        raise NotImplementedError

    def countries(self, *, include_inactive: bool = False) -> tuple[Country, ...]:
        rows = self._all()
        if include_inactive:
            return rows
        return tuple(c for c in rows if c.active)

    def country(self, code: CountryCode) -> Country | None:
        return next((c for c in self._all() if c.code == code), None)

    def require_country(self, code: CountryCode) -> Country:
        found = self.country(code)
        if found is None or not found.active:
            raise UnsupportedCountry(country=code.value)
        return found

    def operators(self, code: CountryCode) -> tuple[Operator, ...]:
        found = self.country(code)
        return found.operators if found is not None else ()

    def operator_for_msisdn(self, msisdn: Msisdn) -> Operator | None:
        try:
            iso = msisdn.country_code.value
        except ValueError:
            return None
        found = self.country(CountryCode(iso))
        return found.operator_for(msisdn) if found is not None else None

    def is_supported(self, country: CountryCode) -> bool:
        found = self.country(country)
        return found is not None and found.active

    def currency_for(self, country: CountryCode) -> Currency:
        return self.require_country(country).currency


__all__ = ["Country", "Operator", "ReferenceDirectory", "_DirectoryMixin"]
