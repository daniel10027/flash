"""Tests du VO Pin (BE-008)."""

from __future__ import annotations

import pytest

from flash.domain.identity.pin import Pin


class TestPinValidation:
    @pytest.mark.parametrize("value", ["1397", "50829", "284016"])
    def test_valid_pins(self, value: str) -> None:
        assert Pin(value).value == value

    @pytest.mark.parametrize("value", ["", "12", "123", "1234567", "abcd", "12 34", "12a4"])
    def test_wrong_length_or_non_digit_rejected(self, value: str) -> None:
        with pytest.raises(ValueError, match="4 à 6 chiffres"):
            Pin(value)

    @pytest.mark.parametrize("value", ["0000", "1111", "999999"])
    def test_repeated_digits_rejected(self, value: str) -> None:
        with pytest.raises(ValueError, match="trop simple"):
            Pin(value)

    @pytest.mark.parametrize("value", ["1234", "3456", "123456"])
    def test_ascending_sequences_rejected(self, value: str) -> None:
        with pytest.raises(ValueError, match="trop simple"):
            Pin(value)

    @pytest.mark.parametrize("value", ["4321", "6543", "654321"])
    def test_descending_sequences_rejected(self, value: str) -> None:
        with pytest.raises(ValueError, match="trop simple"):
            Pin(value)


class TestPinSecrecy:
    def test_repr_hides_value(self) -> None:
        assert "1397" not in repr(Pin("1397"))
        assert repr(Pin("1397")) == "Pin(len=4, value='***')"

    def test_str_hides_value(self) -> None:
        assert str(Pin("1397")) == "***"

    def test_is_value_object(self) -> None:
        assert Pin("1397") == Pin("1397")
        assert Pin("1397") != Pin("2468")
