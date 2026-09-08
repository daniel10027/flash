"""``LedgerAccount`` — un compte du grand livre."""

from __future__ import annotations

from dataclasses import dataclass

from flash.domain.ledger.chart import AccountType, Direction, normal_balance
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import Currency, Money


@dataclass(frozen=True, slots=True)
class LedgerAccount:
    """Compte comptable identifié, typé, mono-devise.

    ``owner_ref`` rattache le compte à un tiers (id utilisateur, agent, marchand) ou
    vaut ``None`` pour les comptes système (produits de frais, arrondi…).
    """

    id: EntityId
    type: AccountType
    currency: Currency
    owner_ref: str | None = None

    @property
    def normal_balance(self) -> Direction:
        return normal_balance(self.type)

    def signed_amount(self, direction: Direction, amount: Money) -> Money:
        """Impact signé d'un mouvement sur le solde du compte (positif = augmentation)."""
        if amount.currency != self.currency:
            raise ValueError("Devise du mouvement différente de celle du compte.")
        return amount if direction is self.normal_balance else -amount


__all__ = ["LedgerAccount"]
