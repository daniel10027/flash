"""Grille tarifaire par défaut (BE-025 / BE-063).

Aucune valeur n'est codée en dur dans le domaine : ces règles alimentent le port
``PricingRuleRepository``. Elles restent **paramétrées par pays** — la Côte d'Ivoire
facture le transfert à 80 bps (0,8 %), le Sénégal à 100 bps : c'est la preuve que le
calcul est générique. Le référentiel éditable en base arrive avec ``BE-062``.
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
_XAF = Currency.of("XAF")

# (code pays, devise, bps du transfert P2P)
_TRANSFER_BPS: dict[str, tuple[Currency, int]] = {
    "CI": (_XOF, 80),
    "SN": (_XOF, 100),
    "ML": (_XOF, 80),
    "BF": (_XOF, 80),
    "BJ": (_XOF, 80),
    "TG": (_XOF, 80),
    "NE": (_XOF, 80),
    "GW": (_XOF, 80),
    "CM": (_XAF, 90),
    "GA": (_XAF, 90),
}


def _default_rules() -> list[PricingRule]:
    rules: list[PricingRule] = []
    for code, (currency, bps) in _TRANSFER_BPS.items():
        country = CountryCode(code)
        rules.append(
            PricingRule(
                country=country,
                operation=OperationType.TRANSFER,
                currency=currency,
                percent_bps=bps,
                min_fee=Money(1, currency),
                rounding=RoundingRule.UP_TO_UNIT,
            )
        )
        rules.append(
            PricingRule(
                country=country,
                operation=OperationType.MERCHANT_PAYMENT,
                currency=currency,
                percent_bps=0,  # gratuit pour le client
            )
        )
        rules.append(
            PricingRule(
                country=country,
                operation=OperationType.OPERATOR_PAYOUT,
                currency=currency,
                percent_bps=150,  # 1,5 % — interop sortante
                min_fee=Money(25, currency),
                rounding=RoundingRule.UP_TO_UNIT,
            )
        )
        rules.append(
            PricingRule(
                country=country,
                operation=OperationType.OPERATOR_COLLECT,
                currency=currency,
                percent_bps=100,  # 1,0 % — interop entrante
                min_fee=Money(10, currency),
                rounding=RoundingRule.UP_TO_UNIT,
            )
        )
    return rules


def build_pricing_repository() -> InMemoryPricingRuleRepository:
    return InMemoryPricingRuleRepository(_default_rules())


__all__ = ["build_pricing_repository"]
