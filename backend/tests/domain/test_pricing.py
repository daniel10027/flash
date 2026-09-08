"""Tests de la tarification : PricingRule, Fee, PricingService (BE-012)."""

from __future__ import annotations

import pytest

from flash.domain.pricing.pricing import (
    Fee,
    InMemoryPricingRuleRepository,
    PricingRule,
    PricingService,
    RoundingRule,
)
from flash.domain.shared.identifiers import CountryCode
from flash.domain.shared.money import XOF, Currency, Money
from flash.domain.shared.operations import OperationType

CI = CountryCode("CI")
SN = CountryCode("SN")
EUR = Currency.of("EUR")


def xof(n: int) -> Money:
    return Money(n, XOF)


def transfer_rule(**overrides: object) -> PricingRule:
    params: dict[str, object] = {
        "country": CI,
        "operation": OperationType.TRANSFER,
        "currency": XOF,
        "percent_bps": 80,
        "rounding": RoundingRule.HALF_UP,
    }
    params.update(overrides)
    return PricingRule(**params)  # type: ignore[arg-type]


class TestRoundingRule:
    def test_decimal_modes_distinct(self) -> None:
        modes = {r.decimal_mode for r in RoundingRule}
        assert len(modes) == 3


class TestFee:
    def test_zero_and_flat(self) -> None:
        assert Fee.zero(XOF).is_zero
        fee = Fee.flat(xof(80))
        assert fee.total == xof(80)
        assert dict(fee.breakdown) == {"flash": xof(80)}

    def test_negative_total_rejected(self) -> None:
        with pytest.raises(ValueError, match="négatif"):
            Fee(total=xof(-1))

    def test_breakdown_must_sum_to_total(self) -> None:
        with pytest.raises(ValueError, match="ventilation"):
            Fee(total=xof(100), breakdown={"flash": xof(60), "operator": xof(30)})

    def test_breakdown_currency_must_match(self) -> None:
        with pytest.raises(ValueError, match="devise"):
            Fee(total=xof(100), breakdown={"flash": Money(100, EUR)})

    def test_breakdown_is_immutable(self) -> None:
        fee = Fee.flat(xof(80))
        with pytest.raises(TypeError):
            fee.breakdown["flash"] = xof(1)  # type: ignore[index]

    def test_default_breakdown_is_flash_only(self) -> None:
        assert dict(Fee(total=xof(80)).breakdown) == {"flash": xof(80)}


class TestPricingRuleValidation:
    @pytest.mark.parametrize("bps", [-1, 10_001])
    def test_bps_out_of_range_rejected(self, bps: int) -> None:
        with pytest.raises(ValueError, match="percent_bps"):
            transfer_rule(percent_bps=bps)

    def test_fee_component_wrong_currency_rejected(self) -> None:
        with pytest.raises(ValueError, match="devise de la règle"):
            transfer_rule(min_fee=Money(1, EUR))

    def test_negative_fee_component_rejected(self) -> None:
        with pytest.raises(ValueError, match="négatif"):
            transfer_rule(fixed_fee=xof(-5))

    def test_min_greater_than_max_rejected(self) -> None:
        with pytest.raises(ValueError, match="min_fee"):
            transfer_rule(min_fee=xof(500), max_fee=xof(100))


class TestPricingRuleCompute:
    def test_transfer_08_percent_half_up(self) -> None:
        assert transfer_rule().compute(xof(10_000)).total == xof(80)
        # 12 345 * 0,8 % = 98,76 -> 99
        assert transfer_rule().compute(xof(12_345)).total == xof(99)

    def test_rounding_up_to_unit(self) -> None:
        rule = transfer_rule(rounding=RoundingRule.UP_TO_UNIT)
        assert rule.compute(xof(12_345)).total == xof(99)
        assert rule.compute(xof(12_301)).total == xof(99)  # 98,408 -> 99

    def test_rounding_down_to_unit(self) -> None:
        rule = transfer_rule(rounding=RoundingRule.DOWN_TO_UNIT)
        assert rule.compute(xof(12_345)).total == xof(98)

    def test_fixed_fee_added_on_top(self) -> None:
        rule = transfer_rule(percent_bps=0, fixed_fee=xof(25))
        assert rule.compute(xof(10_000)).total == xof(25)

    def test_min_fee_floor_applied(self) -> None:
        rule = transfer_rule(min_fee=xof(50))
        assert rule.compute(xof(1_000)).total == xof(50)  # 0,8 % = 8 -> plancher 50

    def test_max_fee_cap_applied(self) -> None:
        rule = transfer_rule(max_fee=xof(1_000))
        assert rule.compute(xof(1_000_000)).total == xof(1_000)  # 0,8 % = 8000 -> plafond

    def test_amount_wrong_currency_rejected(self) -> None:
        with pytest.raises(ValueError, match="devise de la règle"):
            transfer_rule().compute(Money(10_000, EUR))

    @pytest.mark.parametrize("bad", [0, -1])
    def test_non_positive_amount_rejected(self, bad: int) -> None:
        with pytest.raises(ValueError, match="strictement positif"):
            transfer_rule().compute(xof(bad))


class TestPricingService:
    def _service(self, *rules: PricingRule) -> PricingService:
        return PricingService(InMemoryPricingRuleRepository(list(rules)))

    def test_uses_matching_rule(self) -> None:
        svc = self._service(transfer_rule())
        fee = svc.fee_for(country=CI, operation=OperationType.TRANSFER, amount=xof(10_000))
        assert fee.total == xof(80)

    def test_missing_rule_means_free(self) -> None:
        svc = self._service(transfer_rule())
        fee = svc.fee_for(country=CI, operation=OperationType.CASH_DEPOSIT, amount=xof(10_000))
        assert fee.is_zero
        # pays sans règle
        fee_sn = svc.fee_for(country=SN, operation=OperationType.TRANSFER, amount=xof(10_000))
        assert fee_sn.is_zero

    def test_per_country_rules_are_independent(self) -> None:
        svc = self._service(
            transfer_rule(),
            transfer_rule(country=SN, percent_bps=120),  # 1,2 % au Sénégal
        )
        ci = svc.fee_for(country=CI, operation=OperationType.TRANSFER, amount=xof(10_000))
        sn = svc.fee_for(country=SN, operation=OperationType.TRANSFER, amount=xof(10_000))
        assert (ci.total, sn.total) == (xof(80), xof(120))

    def test_repository_add_overwrites_same_key(self) -> None:
        repo = InMemoryPricingRuleRepository([transfer_rule()])
        repo.add(transfer_rule(percent_bps=100))
        assert repo.rule_for(CI, OperationType.TRANSFER).percent_bps == 100  # type: ignore[union-attr]
