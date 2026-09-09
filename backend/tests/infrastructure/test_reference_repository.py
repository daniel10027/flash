"""Intégration : ``seed_reference`` + ``SqlAlchemyReferenceDirectory`` (BE-061)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session, sessionmaker

from flash.domain.shared.identifiers import CountryCode, Msisdn
from flash.domain.shared.money import Currency
from flash.infrastructure.reference import SqlAlchemyReferenceDirectory, seed_reference

pytestmark = pytest.mark.integration


def test_seed_then_read_back(session_factory: sessionmaker[Session]) -> None:
    written = seed_reference(session_factory)
    assert written == 10

    directory = SqlAlchemyReferenceDirectory(session_factory)
    codes = {c.code.value for c in directory.countries()}
    assert {"CI", "SN", "CM", "GA"} <= codes
    assert directory.currency_for(CountryCode("CM")) == Currency.of("XAF")

    orange = directory.operator_for_msisdn(Msisdn("+2250712345678"))
    assert orange is not None and orange.code == "ORANGE_CI"

    ci = directory.require_country(CountryCode("CI"))
    assert {o.code for o in ci.operators} >= {"ORANGE_CI", "MTN_CI", "MOOV_CI"}


def test_seed_is_idempotent(session_factory: sessionmaker[Session]) -> None:
    seed_reference(session_factory)
    seed_reference(session_factory)  # ne doit pas dupliquer d'opérateurs
    directory = SqlAlchemyReferenceDirectory(session_factory)
    ci = directory.require_country(CountryCode("CI"))
    assert len(ci.operators) == len({o.code for o in ci.operators})
