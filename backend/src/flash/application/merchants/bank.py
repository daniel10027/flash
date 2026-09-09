"""Port ``BankGateway`` — la frontière avec la banque partenaire pour les virements de
règlement marchand (BE-070).

Le virement est ici traité **synchrone** pour le sandbox : ``transfer`` renvoie
``accepted`` + une référence bancaire. Un connecteur réel remplacera
``SandboxBankGateway`` (virements SEPA/instantané, statuts asynchrones).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class BankAck:
    accepted: bool
    bank_reference: str
    reason: str | None = None


@runtime_checkable
class BankGateway(Protocol):
    def transfer(
        self,
        *,
        holder: str,
        iban: str,
        bank_name: str,
        amount_minor: int,
        currency: str,
        reference: str,
    ) -> BankAck: ...


__all__ = ["BankAck", "BankGateway"]
