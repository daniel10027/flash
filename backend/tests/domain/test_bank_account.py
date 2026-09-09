"""Tests du value object ``BankAccount`` (BE-070)."""

from __future__ import annotations

import pytest

from flash.domain.merchants.bank_account import BankAccount


class TestBankAccount:
    def test_normalises_fields(self) -> None:
        account = BankAccount(
            holder="  SARL Chez Awa  ",
            iban="ci93 ci00 8011 1301 1342 9120 0589",
            bank_name="  Ecobank CI  ",
        )
        assert account.holder == "SARL Chez Awa"
        assert account.iban == "CI93CI0080111301134291200589"
        assert account.bank_name == "Ecobank CI"

    def test_masked_hides_middle(self) -> None:
        account = BankAccount(
            holder="Awa", iban="CI93CI0080111301134291200589", bank_name="Ecobank"
        )
        assert account.masked() == "CI93…0589"

    def test_masked_returns_full_when_short(self) -> None:
        account = BankAccount(holder="Awa", iban="CI930080", bank_name="Ecobank")
        assert account.masked() == "CI930080"

    def test_blank_holder_rejected(self) -> None:
        with pytest.raises(ValueError, match="titulaire"):
            BankAccount(holder="   ", iban="CI93CI0080111301", bank_name="Ecobank")

    def test_blank_bank_name_rejected(self) -> None:
        with pytest.raises(ValueError, match="banque"):
            BankAccount(holder="Awa", iban="CI93CI0080111301", bank_name="  ")

    @pytest.mark.parametrize("iban", ["CI93", "CI93-CI00-8011", "CI93 CI00 80@1"])
    def test_invalid_iban_rejected(self, iban: str) -> None:
        with pytest.raises(ValueError, match="IBAN"):
            BankAccount(holder="Awa", iban=iban, bank_name="Ecobank")
