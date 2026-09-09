"""Compte bancaire de règlement d'un marchand (value object)."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BankAccount:
    holder: str
    iban: str
    bank_name: str

    def __post_init__(self) -> None:
        if not self.holder.strip():
            raise ValueError("Le titulaire du compte est requis.")
        cleaned = self.iban.replace(" ", "")
        if len(cleaned) < 8 or not cleaned.isalnum():
            raise ValueError("IBAN / RIB invalide.")
        if not self.bank_name.strip():
            raise ValueError("Le nom de la banque est requis.")
        object.__setattr__(self, "holder", self.holder.strip())
        object.__setattr__(self, "iban", cleaned.upper())
        object.__setattr__(self, "bank_name", self.bank_name.strip())

    def masked(self) -> str:
        return f"{self.iban[:4]}…{self.iban[-4:]}" if len(self.iban) > 8 else self.iban


__all__ = ["BankAccount"]
