"""Intégration : grille tarifaire & plafonds éditables en base (reste de BE-062)."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session, sessionmaker

from flash.domain.identity.kyc import KycTier
from flash.domain.limits.limits import LimitRule
from flash.domain.pricing.pricing import PricingRule, RoundingRule
from flash.domain.shared.identifiers import CountryCode
from flash.domain.shared.money import Currency, Money
from flash.domain.shared.operations import OperationType
from flash.infrastructure.limits import (
    SqlAlchemyLimitEditor,
    SqlAlchemyLimitRuleRepository,
    seed_limits,
)
from flash.infrastructure.pricing import (
    SqlAlchemyPricingEditor,
    SqlAlchemyPricingRuleRepository,
    seed_pricing,
)

pytestmark = pytest.mark.integration

XOF = Currency.of("XOF")


def test_pricing_editor_roundtrip_and_repository_read(
    session_factory: sessionmaker[Session],
) -> None:
    editor = SqlAlchemyPricingEditor(session_factory)
    repo = SqlAlchemyPricingRuleRepository(session_factory)

    editor.upsert(
        PricingRule(
            country=CountryCode("CI"),
            operation=OperationType.TRANSFER,
            currency=XOF,
            percent_bps=88,
            min_fee=Money(5, XOF),
            rounding=RoundingRule.UP_TO_UNIT,
        )
    )
    got = repo.rule_for(CountryCode("CI"), OperationType.TRANSFER)
    assert got is not None
    assert got.percent_bps == 88 and got.min_fee == Money(5, XOF)
    assert got.rounding is RoundingRule.UP_TO_UNIT

    editor.upsert(
        PricingRule(
            country=CountryCode("CI"),
            operation=OperationType.TRANSFER,
            currency=XOF,
            percent_bps=91,
        )
    )
    assert repo.rule_for(CountryCode("CI"), OperationType.TRANSFER).percent_bps == 91

    editor.delete(CountryCode("CI"), OperationType.TRANSFER)
    assert repo.rule_for(CountryCode("CI"), OperationType.TRANSFER) is None


def test_limit_editor_roundtrip_and_repository_read(
    session_factory: sessionmaker[Session],
) -> None:
    editor = SqlAlchemyLimitEditor(session_factory)
    repo = SqlAlchemyLimitRuleRepository(session_factory)

    editor.upsert(
        LimitRule(
            country=CountryCode("SN"),
            kyc_tier=KycTier.TIER_1,
            operation=OperationType.TRANSFER,
            per_tx=Money(1_200_000, XOF),
            balance_max=Money(4_000_000, XOF),
        )
    )
    got = repo.rule_for(CountryCode("SN"), KycTier.TIER_1, OperationType.TRANSFER)
    assert got is not None
    assert got.per_tx == Money(1_200_000, XOF)
    assert got.balance_max == Money(4_000_000, XOF)
    assert got.daily is None

    editor.delete(CountryCode("SN"), KycTier.TIER_1, OperationType.TRANSFER)
    assert (
        repo.rule_for(CountryCode("SN"), KycTier.TIER_1, OperationType.TRANSFER) is None
    )


def test_seed_is_idempotent(session_factory: sessionmaker[Session]) -> None:
    assert seed_pricing(session_factory) == seed_pricing(session_factory)
    assert seed_limits(session_factory) == seed_limits(session_factory)
    editor = SqlAlchemyPricingEditor(session_factory)
    keys = {(r.country.value, r.operation.value) for r in editor.all()}
    assert ("CI", "TRANSFER") in keys and ("CM", "OPERATOR_PAYOUT") in keys
    limit_editor = SqlAlchemyLimitEditor(session_factory)
    assert len(limit_editor.all()) == len(
        {(r.country.value, int(r.kyc_tier), r.operation.value) for r in limit_editor.all()}
    )
