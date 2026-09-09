"""Implémentations du référentiel pays / opérateurs (BE-061).

- ``StaticReferenceDirectory`` : jeu de données intégré (UEMOA / CEMAC), utilisé pour le
  bootstrap, les tests, et comme source du ``flash reference seed``.
- ``SqlAlchemyReferenceDirectory`` : lecture depuis les tables ``countries`` /
  ``operators`` (sessions propres, hors Unit of Work applicative).
- ``CachingReferenceDirectory`` : garde un instantané en mémoire, revalidé contre une
  **version** stockée dans Redis (``flash:reference:version``). ``bump()`` invalide tous
  les workers ; ``reload()`` force un rechargement local.
"""

from __future__ import annotations

import time
from collections.abc import Callable

from redis import Redis
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from flash.domain.country.reference import Country, Operator, _DirectoryMixin
from flash.domain.shared.errors import InvalidAccountState
from flash.domain.shared.identifiers import CountryCode
from flash.domain.shared.money import Currency
from flash.infrastructure.db.mappers import (
    country_to_domain,
    country_to_models,
    operator_to_domain,
    operator_to_model,
)
from flash.infrastructure.db.models import CountryModel, OperatorModel

_VERSION_KEY = "flash:reference:version"
_LOCAL_TTL_SECONDS = 30.0


def _xof(country: str, *, name: str, dialing: str, tz: str, operators: list[Operator]) -> Country:
    return Country(
        code=CountryCode(country),
        name=name,
        currency=Currency.of("XOF"),
        dialing_code=dialing,
        timezone=tz,
        operators=tuple(operators),
    )


def _op(country: str, code: str, name: str, prefixes: tuple[str, ...]) -> Operator:
    return Operator(code=code, name=name, country=CountryCode(country), msisdn_prefixes=prefixes)


def _static_countries() -> tuple[Country, ...]:
    return (
        _xof(
            "CI",
            name="Côte d'Ivoire",
            dialing="225",
            tz="Africa/Abidjan",
            operators=[
                _op("CI", "ORANGE_CI", "Orange Money", ("07", "27")),
                _op("CI", "MTN_CI", "MTN MoMo", ("05", "25")),
                _op("CI", "MOOV_CI", "Moov Money", ("01", "21")),
                _op("CI", "WAVE_CI", "Wave", ()),
            ],
        ),
        _xof(
            "SN",
            name="Sénégal",
            dialing="221",
            tz="Africa/Dakar",
            operators=[
                _op("SN", "ORANGE_SN", "Orange Money", ("77", "78")),
                _op("SN", "FREE_SN", "Free Money", ("76",)),
                _op("SN", "EXPRESSO_SN", "E-Money", ("70",)),
                _op("SN", "WAVE_SN", "Wave", ()),
            ],
        ),
        _xof("ML", name="Mali", dialing="223", tz="Africa/Bamako", operators=[]),
        _xof("BF", name="Burkina Faso", dialing="226", tz="Africa/Ouagadougou", operators=[]),
        _xof("BJ", name="Bénin", dialing="229", tz="Africa/Porto-Novo", operators=[]),
        _xof("TG", name="Togo", dialing="228", tz="Africa/Lome", operators=[]),
        _xof("NE", name="Niger", dialing="227", tz="Africa/Niamey", operators=[]),
        _xof("GW", name="Guinée-Bissau", dialing="245", tz="Africa/Bissau", operators=[]),
        Country(
            code=CountryCode("CM"),
            name="Cameroun",
            currency=Currency.of("XAF"),
            dialing_code="237",
            timezone="Africa/Douala",
            operators=(
                _op("CM", "ORANGE_CM", "Orange Money", ("69", "65")),
                _op("CM", "MTN_CM", "MTN MoMo", ("67", "68", "650", "651", "652", "653", "654")),
            ),
        ),
        Country(
            code=CountryCode("GA"),
            name="Gabon",
            currency=Currency.of("XAF"),
            dialing_code="241",
            timezone="Africa/Libreville",
            operators=(
                _op("GA", "AIRTEL_GA", "Airtel Money", ("07", "04")),
                _op("GA", "MOOV_GA", "Moov Money", ("06", "02", "05")),
            ),
        ),
    )


class StaticReferenceDirectory(_DirectoryMixin):
    def __init__(self, countries: tuple[Country, ...] | None = None) -> None:
        self._countries = countries if countries is not None else _static_countries()

    def _all(self) -> tuple[Country, ...]:
        return self._countries


class SqlAlchemyReferenceDirectory(_DirectoryMixin):
    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def _all(self) -> tuple[Country, ...]:
        with self._session_factory() as session:
            stmt = select(CountryModel).order_by(CountryModel.code.asc())
            return tuple(country_to_domain(m) for m in session.scalars(stmt))


class CachingReferenceDirectory(_DirectoryMixin):
    def __init__(self, inner: _DirectoryMixin, redis: Redis[bytes]) -> None:
        self._inner = inner
        self._redis = redis
        self._snapshot: tuple[Country, ...] = ()
        self._version: bytes | None = None
        self._checked_at = 0.0

    def _all(self) -> tuple[Country, ...]:
        now = time.monotonic()
        if self._snapshot and now - self._checked_at < _LOCAL_TTL_SECONDS:
            return self._snapshot
        self._checked_at = now
        current = self._redis.get(_VERSION_KEY)
        if not self._snapshot or current != self._version:
            self._snapshot = self._inner._all()
            self._version = current
        return self._snapshot

    def reload(self) -> None:
        self._snapshot = self._inner._all()
        self._version = self._redis.get(_VERSION_KEY)
        self._checked_at = time.monotonic()

    def bump(self) -> int:
        """Incrémente la version : tous les workers rechargeront au prochain accès."""
        value = int(self._redis.incr(_VERSION_KEY))
        self._snapshot = ()
        return value


class MutableReferenceDirectory(_DirectoryMixin):
    """Référentiel en mémoire, à la fois lisible et éditable (bootstrap statique + tests)."""

    def __init__(self, countries: tuple[Country, ...] | None = None) -> None:
        rows = countries if countries is not None else _static_countries()
        self._by_code: dict[str, Country] = {c.code.value: c for c in rows}

    def _all(self) -> tuple[Country, ...]:
        return tuple(sorted(self._by_code.values(), key=lambda c: c.code.value))

    # --- ReferenceEditor
    def save_country(self, country: Country) -> None:
        existing = self._by_code.get(country.code.value)
        operators = country.operators or (existing.operators if existing else ())
        self._by_code[country.code.value] = Country(
            code=country.code,
            name=country.name,
            currency=country.currency,
            dialing_code=country.dialing_code,
            timezone=country.timezone,
            active=country.active,
            operators=operators,
        )

    def remove_country(self, code: CountryCode) -> None:
        self._by_code.pop(code.value, None)

    def operator(self, code: str) -> Operator | None:
        for country in self._by_code.values():
            for operator in country.operators:
                if operator.code == code:
                    return operator
        return None

    def save_operator(self, operator: Operator) -> None:
        country = self._by_code.get(operator.country.value)
        if country is None:
            raise InvalidAccountState(f"Pays inconnu : {operator.country.value}.")
        kept = tuple(o for o in country.operators if o.code != operator.code)
        self._replace_operators(country, (*kept, operator))

    def remove_operator(self, code: str) -> None:
        for country in list(self._by_code.values()):
            if any(o.code == code for o in country.operators):
                self._replace_operators(
                    country, tuple(o for o in country.operators if o.code != code)
                )
                return

    def _replace_operators(self, country: Country, operators: tuple[Operator, ...]) -> None:
        self._by_code[country.code.value] = Country(
            code=country.code,
            name=country.name,
            currency=country.currency,
            dialing_code=country.dialing_code,
            timezone=country.timezone,
            active=country.active,
            operators=tuple(sorted(operators, key=lambda o: o.code)),
        )


class SqlAlchemyReferenceEditor:
    def __init__(
        self,
        session_factory: sessionmaker[Session],
        *,
        on_change: Callable[[], object] | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._on_change = on_change

    def _invalidate(self) -> None:
        if self._on_change is not None:
            self._on_change()

    def country(self, code: CountryCode) -> Country | None:
        with self._session_factory() as session:
            model = session.get(CountryModel, code.value)
            return country_to_domain(model) if model is not None else None

    def save_country(self, country: Country) -> None:
        country_model, operator_models = country_to_models(country)
        with self._session_factory() as session:
            session.merge(country_model)
            if country.operators:
                for operator_model in operator_models:
                    session.merge(operator_model)
            session.commit()
        self._invalidate()

    def remove_country(self, code: CountryCode) -> None:
        with self._session_factory() as session:
            model = session.get(CountryModel, code.value)
            if model is not None:
                session.delete(model)
                session.commit()
        self._invalidate()

    def operator(self, code: str) -> Operator | None:
        with self._session_factory() as session:
            model = session.get(OperatorModel, code)
            return operator_to_domain(model) if model is not None else None

    def save_operator(self, operator: Operator) -> None:
        with self._session_factory() as session:
            if session.get(CountryModel, operator.country.value) is None:
                raise InvalidAccountState(f"Pays inconnu : {operator.country.value}.")
            session.merge(operator_to_model(operator))
            session.commit()
        self._invalidate()

    def remove_operator(self, code: str) -> None:
        with self._session_factory() as session:
            model = session.get(OperatorModel, code)
            if model is not None:
                session.delete(model)
                session.commit()
        self._invalidate()


class ReadOnlyReferenceEditor:
    """Éditeur refusant toute écriture — actif quand ``REFERENCE_SOURCE=static``."""

    _MSG = "Référentiel en lecture seule : passez REFERENCE_SOURCE=db pour l'éditer."

    def country(self, code: CountryCode) -> Country | None:
        return None

    def save_country(self, country: Country) -> None:
        raise InvalidAccountState(self._MSG)

    def remove_country(self, code: CountryCode) -> None:
        raise InvalidAccountState(self._MSG)

    def operator(self, code: str) -> Operator | None:
        return None

    def save_operator(self, operator: Operator) -> None:
        raise InvalidAccountState(self._MSG)

    def remove_operator(self, code: str) -> None:
        raise InvalidAccountState(self._MSG)


def seed_reference(session_factory: sessionmaker[Session]) -> int:
    """Charge / met à jour le jeu de données statique en base. Idempotent."""
    written = 0
    with session_factory() as session:
        for country in _static_countries():
            country_model, operator_models = country_to_models(country)
            session.merge(country_model)
            session.query(OperatorModel).filter(
                OperatorModel.country_code == country.code.value
            ).delete()
            for operator_model in operator_models:
                session.add(operator_model)
            written += 1
        session.commit()
    return written


__all__ = [
    "CachingReferenceDirectory",
    "MutableReferenceDirectory",
    "ReadOnlyReferenceEditor",
    "SqlAlchemyReferenceDirectory",
    "SqlAlchemyReferenceEditor",
    "StaticReferenceDirectory",
    "seed_reference",
]
