"""Tests du VO Money / Currency (BE-003)."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from decimal import Decimal

import pytest

from flash.domain.shared.errors import CurrencyMismatch
from flash.domain.shared.money import XOF, Currency, Money

EUR = Currency.of("EUR")


class TestCurrency:
    def test_of_known_currency_sets_exponent(self) -> None:
        assert XOF.exponent == 0
        assert EUR.exponent == 2
        assert XOF.minor_units_per_unit == 1
        assert EUR.minor_units_per_unit == 100

    def test_unknown_currency_rejected(self) -> None:
        with pytest.raises(ValueError, match="Devise inconnue"):
            Currency.of("XYZ")

    @pytest.mark.parametrize("code", ["xof", "XO", "XOF1", "123"])
    def test_malformed_code_rejected(self, code: str) -> None:
        with pytest.raises(ValueError):
            Currency(code, 0)

    def test_currency_is_value_object(self) -> None:
        assert Currency.of("XOF") == XOF
        assert hash(Currency.of("XOF")) == hash(XOF)

    def test_exponent_out_of_bounds_rejected(self) -> None:
        with pytest.raises(ValueError, match="Exposant"):
            Currency("ABC", 9)
        with pytest.raises(ValueError, match="Exposant"):
            Currency("ABC", -1)

    def test_str_is_code(self) -> None:
        assert str(XOF) == "XOF"


class TestMoneyConstruction:
    def test_zero(self) -> None:
        assert Money.zero(XOF).amount_minor == 0
        assert Money.zero(XOF).is_zero

    def test_from_units_no_subunit(self) -> None:
        assert Money.from_units(10_000, XOF) == Money(10_000, XOF)

    def test_from_units_with_subunit_rounds_half_up(self) -> None:
        assert Money.from_units("10.505", EUR) == Money(1051, EUR)
        assert Money.from_units(Decimal("10.50"), EUR) == Money(1050, EUR)

    def test_float_amount_minor_rejected(self) -> None:
        with pytest.raises(TypeError):
            Money(100.0, XOF)  # type: ignore[arg-type]

    def test_bool_amount_minor_rejected(self) -> None:
        with pytest.raises(TypeError):
            Money(True, XOF)

    def test_sign_predicates(self) -> None:
        assert Money(1, XOF).is_positive
        assert not Money(0, XOF).is_positive
        assert not Money(-1, XOF).is_positive
        assert Money(-1, XOF).is_negative
        assert Money(0, XOF).is_zero

    def test_units_property_is_exact(self) -> None:
        assert Money(1051, EUR).units == Decimal("10.51")
        assert Money(10_000, XOF).units == Decimal("10000")


class TestMoneyArithmetic:
    def test_add_and_sub_same_currency(self) -> None:
        assert Money(700, XOF) + Money(300, XOF) == Money(1000, XOF)
        assert Money(700, XOF) - Money(300, XOF) == Money(400, XOF)

    def test_sub_can_go_negative(self) -> None:
        result = Money(300, XOF) - Money(500, XOF)
        assert result == Money(-200, XOF)
        assert result.is_negative

    def test_neg(self) -> None:
        assert -Money(200, XOF) == Money(-200, XOF)

    def test_mixed_currency_add_rejected(self) -> None:
        with pytest.raises(CurrencyMismatch) as excinfo:
            _ = Money(100, XOF) + Money(100, EUR)
        assert excinfo.value.code == "CURRENCY_MISMATCH"
        assert excinfo.value.details == {"left": "XOF", "right": "EUR"}

    def test_mixed_currency_compare_rejected(self) -> None:
        with pytest.raises(CurrencyMismatch):
            _ = Money(100, XOF) < Money(100, EUR)

    def test_mul_by_int(self) -> None:
        assert Money(150, XOF) * 3 == Money(450, XOF)
        assert 3 * Money(150, XOF) == Money(450, XOF)

    def test_mul_by_non_int_rejected(self) -> None:
        with pytest.raises(TypeError):
            _ = Money(150, XOF) * 1.5  # type: ignore[operator]


class TestMoneyPercentage:
    def test_transfer_fee_0_8_percent_rounds_half_up(self) -> None:
        # 10 000 XOF * 0,8 % = 80 exactement
        assert Money(10_000, XOF).percentage(80) == Money(80, XOF)
        # 12 345 * 0,8 % = 98,76 -> 99 (half up)
        assert Money(12_345, XOF).percentage(80) == Money(99, XOF)

    def test_percentage_floor_rounding(self) -> None:
        from decimal import ROUND_FLOOR

        assert Money(12_345, XOF).percentage(80, rounding=ROUND_FLOOR) == Money(98, XOF)

    def test_percentage_zero(self) -> None:
        assert Money(10_000, XOF).percentage(0) == Money(0, XOF)

    def test_negative_bps_rejected(self) -> None:
        with pytest.raises(ValueError):
            Money(10_000, XOF).percentage(-1)


class TestMoneyComparisonAndDisplay:
    def test_ordering(self) -> None:
        assert Money(100, XOF) < Money(200, XOF)
        assert Money(100, XOF) <= Money(100, XOF)
        assert Money(200, XOF) > Money(100, XOF)
        assert Money(200, XOF) >= Money(200, XOF)
        assert sorted([Money(3, XOF), Money(1, XOF), Money(2, XOF)]) == [
            Money(1, XOF),
            Money(2, XOF),
            Money(3, XOF),
        ]

    @pytest.mark.parametrize("op", ["le", "gt", "ge"])
    def test_mixed_currency_all_comparisons_rejected(self, op: str) -> None:
        import operator

        with pytest.raises(CurrencyMismatch):
            getattr(operator, op)(Money(1, XOF), Money(1, EUR))

    def test_str_no_subunit(self) -> None:
        assert str(Money(10_000, XOF)) == "10000 XOF"

    def test_str_with_subunit(self) -> None:
        assert str(Money(1050, EUR)) == "10.50 EUR"

    def test_with_amount_keeps_currency(self) -> None:
        assert Money(1, XOF).with_amount(999) == Money(999, XOF)

    def test_immutability(self) -> None:
        m = Money(100, XOF)
        with pytest.raises(FrozenInstanceError):
            m.amount_minor = 200  # type: ignore[misc]
