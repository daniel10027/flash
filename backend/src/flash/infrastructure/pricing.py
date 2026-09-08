"""Grille tarifaire statique (BE-025+).

Valeurs par défaut en attendant le référentiel éditable en base (``BE-062``). Le
transfert coûte **0,8 % (80 bps)**, arrondi au franc supérieur, plancher 1 XOF.
"""

from __future__ import annotations

from flash.domain.pricing.pricing import (
    InMemoryPricingRuleRepository,
    PricingRule,
    RoundingRule,
)
from flash.domain.shared.identifiers import CountryCode
from flash.domain.shared.money import Currency, Money
from flash.domain.shared.operations import OperationType

_XOF = Currency.of("XOF")
_XOF_COUNTRIES = ("CI", "SN", "ML", "BF", "BJ", "TG", "NE", "GW")


def _default_rules() -> list[PricingRule]:
    rules: list[PricingRule] = []
    for code in _XOF_COUNTRIES:
        country = CountryCode(code)
        rules.append(
            PricingRule(
                country=country,
                operation=OperationType.TRANSFER,
                currency=_XOF,
                percent_bps=80,  # 0,8 %
                min_fee=Money(1, _XOF),
                rounding=RoundingRule.UP_TO_UNIT,
            )
        )
        rules.append(
            PricingRule(
                country=country,
                operation=OperationType.MERCHANT_PAYMENT,
                currency=_XOF,
                percent_bps=0,  # gratuit pour le client
            )
        )
    return rules


def build_pricing_repository() -> InMemoryPricingRuleRepository:
    return InMemoryPricingRuleRepository(_default_rules())


__all__ = ["build_pricing_repository"]
