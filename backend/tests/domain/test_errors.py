"""Tests de la hiérarchie d'erreurs de domaine (BE-005)."""

from __future__ import annotations

import pytest

from flash.domain.shared import errors
from flash.domain.shared.errors import (
    DomainError,
    DuplicateOperation,
    InsufficientFunds,
    KycRequired,
)


def _all_domain_error_classes() -> list[type[DomainError]]:
    return [
        obj
        for obj in vars(errors).values()
        if isinstance(obj, type) and issubclass(obj, DomainError) and obj is not DomainError
    ]


class TestErrorContract:
    @pytest.mark.parametrize("cls", _all_domain_error_classes(), ids=lambda c: c.__name__)
    def test_every_error_has_stable_code_and_message(self, cls: type[DomainError]) -> None:
        assert cls.code and cls.code.isupper()
        assert cls.code.replace("_", "").isalpha()
        assert cls.message and cls.message != DomainError.message

    def test_codes_are_unique(self) -> None:
        codes = [c.code for c in _all_domain_error_classes()]
        assert len(codes) == len(set(codes)), "codes d'erreur en double"

    def test_all_are_catchable_as_domain_error(self) -> None:
        for cls in _all_domain_error_classes():
            assert issubclass(cls, DomainError)


class TestErrorBehaviour:
    def test_default_message_used_when_none_given(self) -> None:
        assert InsufficientFunds().message == InsufficientFunds.message

    def test_custom_message_and_details(self) -> None:
        err = InsufficientFunds("Il manque 500 XOF", shortfall=500)
        assert err.message == "Il manque 500 XOF"
        assert err.details == {"shortfall": 500}
        assert "shortfall=500" in str(err)
        assert "[INSUFFICIENT_FUNDS]" in str(err)

    def test_kyc_required_carries_min_tier(self) -> None:
        err = KycRequired(2)
        assert err.details == {"min_tier": 2}
        assert "2" in err.message

    def test_duplicate_operation_is_domain_error(self) -> None:
        with pytest.raises(DomainError):
            raise DuplicateOperation()

    def test_str_without_details(self) -> None:
        expected = "[INSUFFICIENT_FUNDS] Solde insuffisant pour réaliser cette opération."
        assert str(InsufficientFunds()) == expected
