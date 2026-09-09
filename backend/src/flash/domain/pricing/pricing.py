"""Tarification — ``PricingRule``, ``Fee`` et ``PricingService``.

Les frais sont calculés à partir d'une règle **propre au pays et à l'opération** :
pourcentage en points de base (bps), éventuel montant fixe, planchers et plafonds, et
règle d'arrondi. Le transfert en Côte d'Ivoire vaut 80 bps (0,8 %). Aucune valeur n'est
codée en dur : les règles proviennent du référentiel (port ``PricingRuleRepository``).
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP
from enum import StrEnum
from types import MappingProxyType
from typing import Protocol, runtime_checkable

from flash.domain.shared.identifiers import CountryCode
from flash.domain.shared.money import Currency, Money
from flash.domain.shared.operations import OperationType

_BPS_DENOMINATOR = 10_000


class RoundingRule(StrEnum):
    """Sens d'arrondi du montant de frais, à la plus petite unité de la devise."""

    HALF_UP = "HALF_UP"
    UP_TO_UNIT = "UP_TO_UNIT"  # toujours vers le haut (favorable à Flash)
    DOWN_TO_UNIT = "DOWN_TO_UNIT"  # toujours vers le bas (favorable au client)

    @property
    def decimal_mode(self) -> str:
        return {
            RoundingRule.HALF_UP: ROUND_HALF_UP,
            RoundingRule.UP_TO_UNIT: ROUND_CEILING,
            RoundingRule.DOWN_TO_UNIT: ROUND_FLOOR,
        }[self]


@dataclass(frozen=True, slots=True)
class Fee:
    """Frais appliqués à une opération, avec ventilation par bénéficiaire."""

    total: Money
    breakdown: Mapping[str, Money] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if self.total.is_negative:
            raise ValueError("Le montant des frais ne peut pas être négatif.")
        parts = dict(self.breakdown) or {"flash": self.total}
        if any(v.currency != self.total.currency for v in parts.values()):
            raise ValueError("Toutes les parts de frais doivent être dans la même devise.")
        summed = Money.zero(self.total.currency)
        for part in parts.values():
            summed = summed + part
        if summed != self.total:
            raise ValueError(
                f"La ventilation ({summed}) ne correspond pas au total ({self.total})."
            )
        object.__setattr__(self, "breakdown", MappingProxyType(parts))

    @classmethod
    def zero(cls, currency: Currency) -> Fee:
        return cls(total=Money.zero(currency), breakdown={"flash": Money.zero(currency)})

    @classmethod
    def flat(cls, amount: Money) -> Fee:
        return cls(total=amount, breakdown={"flash": amount})

    @property
    def is_zero(self) -> bool:
        return self.total.is_zero


@dataclass(frozen=True, slots=True)
class PricingRule:
    """Règle de calcul des frais pour un couple (pays, opération)."""

    country: CountryCode
    operation: OperationType
    currency: Currency
    percent_bps: int = 0
    fixed_fee: Money | None = None
    min_fee: Money | None = None
    max_fee: Money | None = None
    rounding: RoundingRule = RoundingRule.HALF_UP

    def __post_init__(self) -> None:
        if not 0 <= self.percent_bps <= _BPS_DENOMINATOR:
            raise ValueError("percent_bps doit être entre 0 et 10 000.")
        for label, money in (
            ("fixed_fee", self.fixed_fee),
            ("min_fee", self.min_fee),
            ("max_fee", self.max_fee),
        ):
            if money is None:
                continue
            if money.currency != self.currency:
                raise ValueError(f"{label} doit être dans la devise de la règle ({self.currency}).")
            if money.is_negative:
                raise ValueError(f"{label} ne peut pas être négatif.")
        if self.min_fee is not None and self.max_fee is not None and self.min_fee > self.max_fee:
            raise ValueError("min_fee ne peut pas dépasser max_fee.")

    def compute(self, amount: Money) -> Fee:
        """Applique la règle à ``amount`` et renvoie les ``Fee`` correspondants."""
        if amount.currency != self.currency:
            raise ValueError("Le montant n'est pas dans la devise de la règle.")
        if not amount.is_positive:
            raise ValueError("Le montant doit être strictement positif.")

        fee = amount.percentage(self.percent_bps, rounding=self.rounding.decimal_mode)
        if self.fixed_fee is not None:
            fee = fee + self.fixed_fee
        if self.min_fee is not None and fee < self.min_fee:
            fee = self.min_fee
        if self.max_fee is not None and fee > self.max_fee:
            fee = self.max_fee
        return Fee.flat(fee)


class PricingRuleRepository:
    """Port : fournit la règle tarifaire applicable (impl. dans ``infrastructure``)."""

    def rule_for(self, country: CountryCode, operation: OperationType) -> PricingRule | None:
        raise NotImplementedError


@runtime_checkable
class PricingRuleEditor(Protocol):
    """Port CRUD back-office de la grille tarifaire (impl. dans ``infrastructure``)."""

    def get(self, country: CountryCode, operation: OperationType) -> PricingRule | None: ...

    def all(self) -> list[PricingRule]: ...

    def upsert(self, rule: PricingRule) -> None: ...

    def delete(self, country: CountryCode, operation: OperationType) -> None: ...


class PricingService:
    """Service de domaine : résout la règle applicable et calcule les frais.

    En l'absence de règle pour un couple (pays, opération), l'opération est **gratuite**
    (frais nuls) : c'est un choix explicite (ex. dépôt cash côté client).
    """

    def __init__(self, rules: PricingRuleRepository) -> None:
        self._rules = rules

    def fee_for(self, *, country: CountryCode, operation: OperationType, amount: Money) -> Fee:
        rule = self._rules.rule_for(country, operation)
        if rule is None:
            return Fee.zero(amount.currency)
        return rule.compute(amount)


class InMemoryPricingRuleRepository(PricingRuleRepository):
    """Implémentation simple en mémoire — utile pour le bootstrap et les tests."""

    def __init__(self, rules: list[PricingRule] | None = None) -> None:
        self._by_key: dict[tuple[str, str], PricingRule] = {}
        for rule in rules or []:
            self.add(rule)

    def add(self, rule: PricingRule) -> None:
        self._by_key[(rule.country.value, rule.operation.value)] = rule

    def rule_for(self, country: CountryCode, operation: OperationType) -> PricingRule | None:
        return self._by_key.get((country.value, operation.value))

    # --- surface d'édition (utilisée en mode ``REFERENCE_SOURCE=static`` et en test)
    def get(self, country: CountryCode, operation: OperationType) -> PricingRule | None:
        return self.rule_for(country, operation)

    def all(self) -> list[PricingRule]:
        return [self._by_key[k] for k in sorted(self._by_key)]

    def upsert(self, rule: PricingRule) -> None:
        self.add(rule)

    def delete(self, country: CountryCode, operation: OperationType) -> None:
        self._by_key.pop((country.value, operation.value), None)


__all__ = [
    "Fee",
    "InMemoryPricingRuleRepository",
    "PricingRule",
    "PricingRuleEditor",
    "PricingRuleRepository",
    "PricingService",
    "RoundingRule",
]
