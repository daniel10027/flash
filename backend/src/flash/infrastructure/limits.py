"""Plafonds : jeu par défaut + implémentations éditables en base (BE-025/062/063).

Les plafonds dépendent du **pays**, du **palier KYC** et de l'**opération**. Valeurs par
défaut zone franc (mêmes montants nominaux, devise propre à chaque pays).

* ``build_limit_repository()`` — jeu par défaut en mémoire.
* ``SqlAlchemyLimitRuleRepository`` — lecture directe de la table ``limit_rules``.
* ``SqlAlchemyLimitEditor`` — CRUD back-office (``REFERENCE_SOURCE=db``).
* ``seed_limits()`` — charge le jeu par défaut en base (idempotent).

Le cumul jour / mois est fourni par ``LimitCounter`` ; d'ici son branchement réel le
``NullLimitCounter`` renvoie zéro et les fenêtres ``daily`` / ``monthly`` restent nulles.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from flash.domain.identity.kyc import KycTier
from flash.domain.limits.limits import (
    InMemoryLimitRuleRepository,
    LimitRule,
    LimitWindow,
)
from flash.domain.shared.errors import InvalidAccountState
from flash.domain.shared.identifiers import CountryCode, EntityId
from flash.domain.shared.money import Currency, Money
from flash.domain.shared.operations import OperationType
from flash.infrastructure.db.models import LimitRuleModel

_XOF = Currency.of("XOF")
_XAF = Currency.of("XAF")
# Zone franc : mêmes montants nominaux, devise propre à chaque pays.
_COUNTRIES: dict[str, Currency] = {
    "CI": _XOF,
    "SN": _XOF,
    "ML": _XOF,
    "BF": _XOF,
    "BJ": _XOF,
    "TG": _XOF,
    "NE": _XOF,
    "GW": _XOF,
    "CM": _XAF,
    "GA": _XAF,
}

# per_tx, balance_max par palier KYC (unité mineure de la devise du pays).
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
    OperationType.OPERATOR_PAYOUT,
    OperationType.OPERATOR_COLLECT,
)


def _default_rules() -> list[LimitRule]:
    rules: list[LimitRule] = []
    for code, currency in _COUNTRIES.items():
        country = CountryCode(code)
        for tier, (per_tx, balance_max) in _TIER_CAPS.items():
            for operation in _OPERATIONS:
                rules.append(
                    LimitRule(
                        country=country,
                        kyc_tier=tier,
                        operation=operation,
                        per_tx=Money(per_tx, currency),
                        balance_max=Money(balance_max, currency),
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


# ------------------------------------------------------------------ persistance


def _minor(value: int | None, currency: Currency) -> Money | None:
    return None if value is None else Money(value, currency)


def rule_to_domain(model: LimitRuleModel) -> LimitRule:
    currency = Currency.of(model.currency)
    return LimitRule(
        country=CountryCode(model.country_code),
        kyc_tier=KycTier(model.kyc_tier),
        operation=OperationType(model.operation),
        per_tx=_minor(model.per_tx_minor, currency),
        daily=_minor(model.daily_minor, currency),
        monthly=_minor(model.monthly_minor, currency),
        balance_max=_minor(model.balance_max_minor, currency),
    )


def rule_to_model(rule: LimitRule, *, now: datetime) -> LimitRuleModel:
    def _m(money: Money | None) -> int | None:
        return None if money is None else money.amount_minor

    anchor = rule.per_tx or rule.daily or rule.monthly or rule.balance_max
    if anchor is None:
        raise InvalidAccountState("Une règle de plafond doit fixer au moins un montant.")
    return LimitRuleModel(
        country_code=rule.country.value,
        kyc_tier=int(rule.kyc_tier),
        operation=rule.operation.value,
        currency=anchor.currency.code,
        per_tx_minor=_m(rule.per_tx),
        daily_minor=_m(rule.daily),
        monthly_minor=_m(rule.monthly),
        balance_max_minor=_m(rule.balance_max),
        updated_at=now,
    )


class SqlAlchemyLimitRuleRepository:
    """Lecture directe de ``limit_rules`` (session propre, hors Unit of Work)."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def rule_for(
        self, country: CountryCode, kyc_tier: KycTier, operation: OperationType
    ) -> LimitRule | None:
        key = (country.value, int(kyc_tier), operation.value)
        with self._session_factory() as session:
            model = session.get(LimitRuleModel, key)
            return rule_to_domain(model) if model is not None else None


class SqlAlchemyLimitEditor:
    """CRUD back-office des plafonds. Écrit hors Unit of Work applicative."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get(
        self, country: CountryCode, kyc_tier: KycTier, operation: OperationType
    ) -> LimitRule | None:
        key = (country.value, int(kyc_tier), operation.value)
        with self._session_factory() as session:
            model = session.get(LimitRuleModel, key)
            return rule_to_domain(model) if model is not None else None

    def all(self) -> list[LimitRule]:
        with self._session_factory() as session:
            stmt = select(LimitRuleModel).order_by(
                LimitRuleModel.country_code,
                LimitRuleModel.kyc_tier,
                LimitRuleModel.operation,
            )
            return [rule_to_domain(m) for m in session.scalars(stmt)]

    def upsert(self, rule: LimitRule) -> None:
        with self._session_factory() as session:
            session.merge(rule_to_model(rule, now=datetime.now(UTC)))
            session.commit()

    def delete(
        self, country: CountryCode, kyc_tier: KycTier, operation: OperationType
    ) -> None:
        key = (country.value, int(kyc_tier), operation.value)
        with self._session_factory() as session:
            model = session.get(LimitRuleModel, key)
            if model is not None:
                session.delete(model)
                session.commit()


class ReadOnlyLimitEditor:
    """Éditeur refusant toute écriture — actif quand ``REFERENCE_SOURCE=static``."""

    _MSG = "Plafonds en lecture seule : passez REFERENCE_SOURCE=db pour les éditer."

    def __init__(self, repository: InMemoryLimitRuleRepository) -> None:
        self._repository = repository

    def get(
        self, country: CountryCode, kyc_tier: KycTier, operation: OperationType
    ) -> LimitRule | None:
        return self._repository.rule_for(country, kyc_tier, operation)

    def all(self) -> list[LimitRule]:
        return self._repository.all()

    def upsert(self, rule: LimitRule) -> None:
        raise InvalidAccountState(self._MSG)

    def delete(
        self, country: CountryCode, kyc_tier: KycTier, operation: OperationType
    ) -> None:
        raise InvalidAccountState(self._MSG)


def seed_limits(session_factory: sessionmaker[Session]) -> int:
    """Charge / met à jour le jeu de plafonds par défaut en base. Idempotent."""
    now = datetime.now(UTC)
    written = 0
    with session_factory() as session:
        for rule in _default_rules():
            session.merge(rule_to_model(rule, now=now))
            written += 1
        session.commit()
    return written


__all__ = [
    "NullLimitCounter",
    "ReadOnlyLimitEditor",
    "SqlAlchemyLimitEditor",
    "SqlAlchemyLimitRuleRepository",
    "build_limit_repository",
    "rule_to_domain",
    "rule_to_model",
    "seed_limits",
]
