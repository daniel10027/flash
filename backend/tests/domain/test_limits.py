"""Tests des plafonds et politiques : LimitRule, LimitPolicy, KycPolicy (BE-013)."""

from __future__ import annotations

from uuid import UUID

import pytest

from flash.domain.identity.kyc import KycTier
from flash.domain.limits.limits import (
    InMemoryLimitCounter,
    InMemoryLimitRuleRepository,
    KycPolicy,
    LimitPolicy,
    LimitRule,
    LimitWindow,
)
from flash.domain.shared.errors import BalanceCapExceeded, KycRequired, LimitExceeded
from flash.domain.shared.identifiers import CountryCode, EntityId
from flash.domain.shared.money import XOF, Money
from flash.domain.shared.operations import OperationType

CI = CountryCode("CI")
USER = EntityId(UUID(int=1))
TRANSFER = OperationType.TRANSFER


def xof(n: int) -> Money:
    return Money(n, XOF)


def rule(**overrides: object) -> LimitRule:
    params: dict[str, object] = {
        "country": CI,
        "kyc_tier": KycTier.TIER_0,
        "operation": TRANSFER,
        "per_tx": xof(200_000),
        "daily": xof(500_000),
        "monthly": xof(2_000_000),
        "balance_max": xof(2_000_000),
    }
    params.update(overrides)
    return LimitRule(**params)  # type: ignore[arg-type]


def policy(*rules: LimitRule, counter: InMemoryLimitCounter | None = None) -> LimitPolicy:
    return LimitPolicy(InMemoryLimitRuleRepository(list(rules)), counter or InMemoryLimitCounter())


class TestLimitRule:
    def test_negative_cap_rejected(self) -> None:
        with pytest.raises(ValueError, match="daily"):
            rule(daily=xof(-1))

    def test_cap_for_window(self) -> None:
        r = rule()
        assert r.cap_for(LimitWindow.PER_TX) == xof(200_000)
        assert r.cap_for(LimitWindow.DAILY) == xof(500_000)
        assert r.cap_for(LimitWindow.MONTHLY) == xof(2_000_000)

    def test_none_cap_means_unlimited(self) -> None:
        r = rule(per_tx=None, daily=None, monthly=None)
        assert r.cap_for(LimitWindow.DAILY) is None


class TestLimitPolicyPerTx:
    def test_within_per_tx_passes(self) -> None:
        policy(rule()).check(
            user_id=USER,
            country=CI,
            kyc_tier=KycTier.TIER_0,
            operation=TRANSFER,
            amount=xof(200_000),
        )

    def test_above_per_tx_rejected(self) -> None:
        with pytest.raises(LimitExceeded) as exc:
            policy(rule()).check(
                user_id=USER,
                country=CI,
                kyc_tier=KycTier.TIER_0,
                operation=TRANSFER,
                amount=xof(200_001),
            )
        assert exc.value.details["window"] == "PER_TX"
        assert exc.value.details["limit"] == 200_000

    def test_non_positive_amount_rejected(self) -> None:
        with pytest.raises(ValueError, match="strictement positif"):
            policy(rule()).check(
                user_id=USER, country=CI, kyc_tier=KycTier.TIER_0, operation=TRANSFER, amount=xof(0)
            )


class TestLimitPolicyWindows:
    def test_daily_cumulative_limit(self) -> None:
        counter = InMemoryLimitCounter()
        counter.set(user_id=USER, operation=TRANSFER, window=LimitWindow.DAILY, amount=xof(450_000))
        pol = policy(rule(), counter=counter)
        # 450 000 déjà + 50 000 = 500 000 -> OK (pile au plafond)
        pol.check(
            user_id=USER,
            country=CI,
            kyc_tier=KycTier.TIER_0,
            operation=TRANSFER,
            amount=xof(50_000),
        )
        # + 50 001 -> dépasse
        with pytest.raises(LimitExceeded) as exc:
            pol.check(
                user_id=USER,
                country=CI,
                kyc_tier=KycTier.TIER_0,
                operation=TRANSFER,
                amount=xof(50_001),
            )
        d = exc.value.details
        assert d["window"] == "DAILY"
        assert d["already_used"] == 450_000
        assert d["remaining"] == 50_000

    def test_monthly_limit_enforced(self) -> None:
        counter = InMemoryLimitCounter()
        counter.set(
            user_id=USER, operation=TRANSFER, window=LimitWindow.MONTHLY, amount=xof(1_999_000)
        )
        with pytest.raises(LimitExceeded) as exc:
            policy(rule(), counter=counter).check(
                user_id=USER,
                country=CI,
                kyc_tier=KycTier.TIER_0,
                operation=TRANSFER,
                amount=xof(2_000),
            )
        assert exc.value.details["window"] == "MONTHLY"

    def test_no_rule_means_no_limit(self) -> None:
        policy().check(
            user_id=USER,
            country=CI,
            kyc_tier=KycTier.TIER_0,
            operation=TRANSFER,
            amount=xof(10_000_000),
        )

    def test_window_without_cap_is_skipped(self) -> None:
        counter = InMemoryLimitCounter()
        counter.set(
            user_id=USER, operation=TRANSFER, window=LimitWindow.MONTHLY, amount=xof(9_000_000)
        )
        # daily=None -> fenêtre ignorée ; monthly=None aussi -> aucun cumul vérifié
        policy(rule(daily=None, monthly=None), counter=counter).check(
            user_id=USER,
            country=CI,
            kyc_tier=KycTier.TIER_0,
            operation=TRANSFER,
            amount=xof(100_000),
        )


class TestBalanceCap:
    def test_incoming_credit_exceeding_cap_rejected(self) -> None:
        with pytest.raises(BalanceCapExceeded) as exc:
            policy(rule()).check_balance_cap(
                country=CI,
                kyc_tier=KycTier.TIER_0,
                operation=TRANSFER,
                current_balance=xof(1_900_000),
                incoming=xof(200_000),
            )
        assert exc.value.details["limit"] == 2_000_000

    def test_within_cap_passes(self) -> None:
        policy(rule()).check_balance_cap(
            country=CI,
            kyc_tier=KycTier.TIER_0,
            operation=TRANSFER,
            current_balance=xof(1_000_000),
            incoming=xof(500_000),
        )

    def test_no_rule_or_no_balance_max_passes(self) -> None:
        policy().check_balance_cap(
            country=CI,
            kyc_tier=KycTier.TIER_0,
            operation=TRANSFER,
            current_balance=xof(10_000_000),
            incoming=xof(10_000_000),
        )
        policy(rule(balance_max=None)).check_balance_cap(
            country=CI,
            kyc_tier=KycTier.TIER_0,
            operation=TRANSFER,
            current_balance=xof(10_000_000),
            incoming=xof(10_000_000),
        )


class TestKycPolicy:
    def test_default_minimum_is_tier_0(self) -> None:
        pol = KycPolicy()
        assert pol.minimum_tier_for(TRANSFER) is KycTier.TIER_0
        pol.require(operation=TRANSFER, kyc_tier=KycTier.TIER_0)  # ne lève pas

    def test_operation_requiring_higher_tier(self) -> None:
        pol = KycPolicy({OperationType.OPERATOR_PAYOUT: KycTier.TIER_1})
        with pytest.raises(KycRequired) as exc:
            pol.require(operation=OperationType.OPERATOR_PAYOUT, kyc_tier=KycTier.TIER_0)
        assert exc.value.details == {"min_tier": 1}

    def test_sufficient_tier_passes(self) -> None:
        pol = KycPolicy({OperationType.OPERATOR_PAYOUT: KycTier.TIER_1})
        pol.require(operation=OperationType.OPERATOR_PAYOUT, kyc_tier=KycTier.TIER_2)


class TestInMemoryRepos:
    def test_rule_repository_keys_on_country_tier_operation(self) -> None:
        repo = InMemoryLimitRuleRepository([rule(), rule(kyc_tier=KycTier.TIER_1, per_tx=xof(999))])
        assert repo.rule_for(CI, KycTier.TIER_1, TRANSFER).per_tx == xof(999)  # type: ignore[union-attr]
        assert repo.rule_for(CI, KycTier.TIER_2, TRANSFER) is None
