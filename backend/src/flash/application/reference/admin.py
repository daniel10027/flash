"""CRUD back-office du référentiel pays / opérateurs (BE-062).

Chaque mutation est **tracée** dans le registre d'audit chaîné (qui / quoi / quand /
avant → après) *avant* de renvoyer. L'invalidation du cache est portée par
l'implémentation de ``ReferenceEditor``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from flash.application.reference.queries import CountryView, OperatorView
from flash.domain.audit.entry import AuditEntry
from flash.domain.audit.ports import AuditLog
from flash.domain.country.reference import Country, Operator, ReferenceEditor
from flash.domain.shared.errors import InvalidInput
from flash.domain.shared.identifiers import CountryCode
from flash.domain.shared.money import Currency
from flash.domain.shared.ports import Clock

_RESOURCE_COUNTRY = "country"
_RESOURCE_OPERATOR = "operator"


def _country_state(country: Country) -> dict[str, Any]:
    return {
        "code": country.code.value,
        "name": country.name,
        "currency": country.currency.code,
        "dialing_code": country.dialing_code,
        "timezone": country.timezone,
        "active": country.active,
    }


def _operator_state(operator: Operator) -> dict[str, Any]:
    return {
        "code": operator.code,
        "country": operator.country.value,
        "name": operator.name,
        "msisdn_prefixes": list(operator.msisdn_prefixes),
        "active": operator.active,
    }


def _country_code(raw: str) -> CountryCode:
    try:
        return CountryCode(raw.upper())
    except ValueError as exc:
        raise InvalidInput("Code pays invalide.") from exc


def _currency(raw: str) -> Currency:
    try:
        return Currency.of(raw.upper())
    except ValueError as exc:
        raise InvalidInput(str(exc)) from exc


# ============================================================== pays
@dataclass(frozen=True, slots=True)
class UpsertCountryCommand:
    actor: str
    role: str
    code: str
    name: str
    currency: str
    dialing_code: str
    timezone: str = "UTC"
    active: bool = True


@dataclass(frozen=True, slots=True)
class DeleteCountryCommand:
    actor: str
    role: str
    code: str


class UpsertCountry:
    def __init__(self, *, editor: ReferenceEditor, audit: AuditLog, clock: Clock) -> None:
        self._editor = editor
        self._audit = audit
        self._clock = clock

    def execute(self, command: UpsertCountryCommand) -> CountryView:
        code = _country_code(command.code)
        try:
            country = Country(
                code=code,
                name=command.name,
                currency=_currency(command.currency),
                dialing_code=command.dialing_code,
                timezone=command.timezone or "UTC",
                active=command.active,
            )
        except ValueError as exc:
            raise InvalidInput(str(exc)) from exc

        existing = self._editor.country(code)
        self._editor.save_country(country)
        self._audit.append(
            actor=command.actor,
            role=command.role,
            action="country.update" if existing is not None else "country.create",
            resource_type=_RESOURCE_COUNTRY,
            resource_id=code.value,
            before=_country_state(existing) if existing is not None else None,
            after=_country_state(country),
            now=self._clock.now(),
        )
        saved = self._editor.country(code) or country
        return CountryView.of(saved)


class DeleteCountry:
    def __init__(self, *, editor: ReferenceEditor, audit: AuditLog, clock: Clock) -> None:
        self._editor = editor
        self._audit = audit
        self._clock = clock

    def execute(self, command: DeleteCountryCommand) -> None:
        code = _country_code(command.code)
        existing = self._editor.country(code)
        if existing is None:
            raise InvalidInput("Pays introuvable.")
        self._editor.remove_country(code)
        self._audit.append(
            actor=command.actor,
            role=command.role,
            action="country.delete",
            resource_type=_RESOURCE_COUNTRY,
            resource_id=code.value,
            before=_country_state(existing),
            after=None,
            now=self._clock.now(),
        )


# ============================================================== opérateurs
@dataclass(frozen=True, slots=True)
class UpsertOperatorCommand:
    actor: str
    role: str
    country: str
    code: str
    name: str
    msisdn_prefixes: list[str] = field(default_factory=list)
    active: bool = True


@dataclass(frozen=True, slots=True)
class DeleteOperatorCommand:
    actor: str
    role: str
    code: str


class UpsertOperator:
    def __init__(self, *, editor: ReferenceEditor, audit: AuditLog, clock: Clock) -> None:
        self._editor = editor
        self._audit = audit
        self._clock = clock

    def execute(self, command: UpsertOperatorCommand) -> OperatorView:
        country = _country_code(command.country)
        if self._editor.country(country) is None:
            raise InvalidInput("Pays inconnu pour cet opérateur.")
        try:
            operator = Operator(
                code=command.code,
                name=command.name,
                country=country,
                msisdn_prefixes=tuple(command.msisdn_prefixes),
                active=command.active,
            )
        except ValueError as exc:
            raise InvalidInput(str(exc)) from exc

        existing = self._editor.operator(command.code)
        self._editor.save_operator(operator)
        self._audit.append(
            actor=command.actor,
            role=command.role,
            action="operator.update" if existing is not None else "operator.create",
            resource_type=_RESOURCE_OPERATOR,
            resource_id=command.code,
            before=_operator_state(existing) if existing is not None else None,
            after=_operator_state(operator),
            now=self._clock.now(),
        )
        return OperatorView.of(operator)


class DeleteOperator:
    def __init__(self, *, editor: ReferenceEditor, audit: AuditLog, clock: Clock) -> None:
        self._editor = editor
        self._audit = audit
        self._clock = clock

    def execute(self, command: DeleteOperatorCommand) -> None:
        existing = self._editor.operator(command.code)
        if existing is None:
            raise InvalidInput("Opérateur introuvable.")
        self._editor.remove_operator(command.code)
        self._audit.append(
            actor=command.actor,
            role=command.role,
            action="operator.delete",
            resource_type=_RESOURCE_OPERATOR,
            resource_id=command.code,
            before=_operator_state(existing),
            after=None,
            now=self._clock.now(),
        )


# ============================================================== lecture de l'audit
@dataclass(frozen=True, slots=True)
class ListAuditEntriesCommand:
    limit: int = 100
    before_sequence: int | None = None


class ListAuditEntries:
    def __init__(self, *, audit: AuditLog) -> None:
        self._audit = audit

    def execute(self, command: ListAuditEntriesCommand) -> list[AuditEntry]:
        return self._audit.recent(limit=command.limit, before_sequence=command.before_sequence)


__all__ = [
    "DeleteCountry",
    "DeleteCountryCommand",
    "DeleteOperator",
    "DeleteOperatorCommand",
    "ListAuditEntries",
    "ListAuditEntriesCommand",
    "UpsertCountry",
    "UpsertCountryCommand",
    "UpsertOperator",
    "UpsertOperatorCommand",
]
