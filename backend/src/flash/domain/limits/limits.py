"""Plafonds et politiques d'autorisation : ``LimitRule``, ``LimitPolicy``, ``KycPolicy``.

Les plafonds dépendent du **pays**, du **palier KYC** et de l'**opération**. Ils ne sont
jamais codés en dur : ils viennent du référentiel (port ``LimitRuleRepository``). Le
cumul glissant (jour / mois) est fourni par le port ``LimitCounter``, alimenté par les
projections de lecture.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from typing import Protocol, runtime_checkable

from flash.domain.identity.kyc import KycTier
from flash.domain.shared.errors import BalanceCapExceeded, KycRequired, LimitExceeded
from flash.domain.shared.identifiers import CountryCode, EntityId
from flash.domain.shared.money import XOF, Money
from flash.domain.shared.operations import OperationType


class LimitWindow(StrEnum):
    PER_TX = "PER_TX"
    DAILY = "DAILY"
    MONTHLY = "MONTHLY"


@dataclass(frozen=True, slots=True)
class LimitRule:
    """Plafonds applicables à un couple (pays, palier KYC, opération).

    Un champ à ``None`` signifie « pas de plafond » sur cette fenêtre.
    """

    country: CountryCode
    kyc_tier: KycTier
    operation: OperationType
    per_tx: Money | None = None
    daily: Money | None = None
    monthly: Money | None = None
    balance_max: Money | None = None

    def __post_init__(self) -> None:
        for label, money in (
            ("per_tx", self.per_tx),
            ("daily", self.daily),
            ("monthly", self.monthly),
            ("balance_max", self.balance_max),
        ):
            if money is not None and money.is_negative:
                raise ValueError(f"{label} ne peut pas être négatif.")

    def cap_for(self, window: LimitWindow) -> Money | None:
        return {
            LimitWindow.PER_TX: self.per_tx,
            LimitWindow.DAILY: self.daily,
            LimitWindow.MONTHLY: self.monthly,
        }[window]


@runtime_checkable
class LimitRuleRepository(Protocol):
    def rule_for(
        self, country: CountryCode, kyc_tier: KycTier, operation: OperationType
    ) -> LimitRule | None: ...


@runtime_checkable
class LimitCounter(Protocol):
    """Cumul déjà consommé par un utilisateur sur une opération, par fenêtre glissante."""

    def consumed(
        self, *, user_id: EntityId, operation: OperationType, window: LimitWindow
    ) -> Money: ...


class LimitPolicy:
    """Vérifie qu'une opération respecte les plafonds par transaction, jour et mois."""

    def __init__(self, rules: LimitRuleRepository, counter: LimitCounter) -> None:
        self._rules = rules
        self._counter = counter

    def check(
        self,
        *,
        user_id: EntityId,
        country: CountryCode,
        kyc_tier: KycTier,
        operation: OperationType,
        amount: Money,
    ) -> None:
        if not amount.is_positive:
            raise ValueError("Le montant doit être strictement positif.")
        rule = self._rules.rule_for(country, kyc_tier, operation)
        if rule is None:
            return

        per_tx = rule.cap_for(LimitWindow.PER_TX)
        if per_tx is not None and amount > per_tx:
            raise LimitExceeded(
                "Montant supérieur au plafond par opération.",
                window=LimitWindow.PER_TX.value,
                limit=per_tx.amount_minor,
                requested=amount.amount_minor,
                currency=amount.currency.code,
            )

        for window in (LimitWindow.DAILY, LimitWindow.MONTHLY):
            cap = rule.cap_for(window)
            if cap is None:
                continue
            used = self._counter.consumed(user_id=user_id, operation=operation, window=window)
            if used + amount > cap:
                remaining = cap - used
                raise LimitExceeded(
                    f"Plafond {window.value.lower()} atteint.",
                    window=window.value,
                    limit=cap.amount_minor,
                    already_used=used.amount_minor,
                    remaining=max(remaining.amount_minor, 0),
                    requested=amount.amount_minor,
                    currency=amount.currency.code,
                )

    def check_balance_cap(
        self,
        *,
        country: CountryCode,
        kyc_tier: KycTier,
        operation: OperationType,
        current_balance: Money,
        incoming: Money,
    ) -> None:
        """Refuse un crédit qui ferait dépasser le plafond de solde du palier."""
        rule = self._rules.rule_for(country, kyc_tier, operation)
        if rule is None or rule.balance_max is None:
            return
        if current_balance + incoming > rule.balance_max:
            raise BalanceCapExceeded(
                limit=rule.balance_max.amount_minor,
                current_balance=current_balance.amount_minor,
                incoming=incoming.amount_minor,
                currency=incoming.currency.code,
            )


class KycPolicy:
    """Impose un palier KYC minimum selon l'opération."""

    def __init__(self, minimum_tier: Mapping[OperationType, KycTier] | None = None) -> None:
        self._minimum: dict[OperationType, KycTier] = dict(minimum_tier or {})

    def minimum_tier_for(self, operation: OperationType) -> KycTier:
        return self._minimum.get(operation, KycTier.TIER_0)

    def require(self, *, operation: OperationType, kyc_tier: KycTier) -> None:
        needed = self.minimum_tier_for(operation)
        if kyc_tier < needed:
            raise KycRequired(int(needed))


# ---------------------------------------------------------------- impl. mémoire


class InMemoryLimitRuleRepository:
    def __init__(self, rules: list[LimitRule] | None = None) -> None:
        self._by_key: dict[tuple[str, int, str], LimitRule] = {}
        for rule in rules or []:
            self.add(rule)

    def add(self, rule: LimitRule) -> None:
        self._by_key[(rule.country.value, int(rule.kyc_tier), rule.operation.value)] = rule

    def rule_for(
        self, country: CountryCode, kyc_tier: KycTier, operation: OperationType
    ) -> LimitRule | None:
        return self._by_key.get((country.value, int(kyc_tier), operation.value))


class InMemoryLimitCounter:
    """Compteur de test : on injecte directement les montants déjà consommés."""

    def __init__(self) -> None:
        self._totals: dict[tuple[str, str, str], Money] = {}

    def set(
        self, *, user_id: EntityId, operation: OperationType, window: LimitWindow, amount: Money
    ) -> None:
        self._totals[(str(user_id), operation.value, window.value)] = amount

    def consumed(
        self, *, user_id: EntityId, operation: OperationType, window: LimitWindow
    ) -> Money:
        return self._totals.get((str(user_id), operation.value, window.value), Money.zero(XOF))


__all__ = [
    "InMemoryLimitCounter",
    "InMemoryLimitRuleRepository",
    "KycPolicy",
    "LimitCounter",
    "LimitPolicy",
    "LimitRule",
    "LimitRuleRepository",
    "LimitWindow",
]
