"""Plafonds statiques et compteur de cumul (BE-025+).

Valeurs par défaut UEMOA en attendant le référentiel éditable (``BE-062``). Pour
l'instant seuls ``per_tx`` et ``balance_max`` sont posés ; le cumul jour/mois sera
branché avec la projection ``statement_entries`` (``BE-038``) — d'ici là le
``NullLimitCounter`` renvoie zéro et les règles ``daily``/``monthly`` restent nulles,
donc jamais consultées.
"""

from __future__ import annotations

from flash.domain.identity.kyc import KycTier
from flash.domain.limits.limits import (
    InMemoryLimitRuleRepository,
    LimitRule,
    LimitWindow,
)
from flash.domain.shared.identifiers import CountryCode, EntityId
from flash.domain.shared.money import Currency, Money
from flash.domain.shared.operations import OperationType

_XOF = Currency.of("XOF")
_XOF_COUNTRIES = ("CI", "SN", "ML", "BF", "BJ", "TG", "NE", "GW")

# per_tx, balance_max par palier KYC (en XOF).
_TIER_CAPS: dict[KycTier, tuple[int, int]] = {
    KycTier.TIER_0: (200_000, 300_000),
    KycTier.TIER_1: (1_000_000, 2_000_000),
    KycTier.TIER_2: (5_000_000, 10_000_000),
}


_OPERATIONS = (
    OperationType.TRANSFER,
    OperationType.MERCHANT_PAYMENT,
    OperationType.CASH_DEPOSIT,
    OperationType.CASH_WITHDRAWAL,
)


def _default_rules() -> list[LimitRule]:
    rules: list[LimitRule] = []
    for code in _XOF_COUNTRIES:
        country = CountryCode(code)
        for tier, (per_tx, balance_max) in _TIER_CAPS.items():
            for operation in _OPERATIONS:
                rules.append(
                    LimitRule(
                        country=country,
                        kyc_tier=tier,
                        operation=operation,
                        per_tx=Money(per_tx, _XOF),
                        balance_max=Money(balance_max, _XOF),
                    )
                )
    return rules


def build_limit_repository() -> InMemoryLimitRuleRepository:
    return InMemoryLimitRuleRepository(_default_rules())


class NullLimitCounter:
    """Compteur temporaire : renvoie zéro. Remplacé par un compteur réel en BE-038."""

    def consumed(
        self, *, user_id: EntityId, operation: OperationType, window: LimitWindow
    ) -> Money:
        return Money.zero(_XOF)


__all__ = ["NullLimitCounter", "build_limit_repository"]
