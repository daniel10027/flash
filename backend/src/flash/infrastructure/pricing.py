"""Grille tarifaire : jeu par défaut + implémentations éditables en base (BE-062/063).

Aucune valeur n'est codée en dur dans le domaine : ces règles alimentent le port
``PricingRuleRepository``. Elles restent **paramétrées par pays** — la Côte d'Ivoire
facture le transfert à 80 bps (0,8 %), le Sénégal à 100 bps : preuve que le calcul est
générique.

* ``build_pricing_repository()`` — jeu par défaut en mémoire (bootstrap, tests,
  ``REFERENCE_SOURCE=static``).
* ``SqlAlchemyPricingRuleRepository`` — lecture directe de la table ``pricing_rules``.
* ``SqlAlchemyPricingEditor`` — CRUD back-office (``REFERENCE_SOURCE=db``).
* ``seed_pricing()`` — charge le jeu par défaut en base (idempotent).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from flash.domain.pricing.pricing import (
    InMemoryPricingRuleRepository,
    PricingRule,
    PricingRuleRepository,
    RoundingRule,
)
from flash.domain.shared.errors import InvalidAccountState
from flash.domain.shared.identifiers import CountryCode
from flash.domain.shared.money import Currency, Money
from flash.domain.shared.operations import OperationType
from flash.infrastructure.db.models import PricingRuleModel

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


# ------------------------------------------------------------------ persistance


def _minor(value: int | None, currency: Currency) -> Money | None:
    return None if value is None else Money(value, currency)


def rule_to_domain(model: PricingRuleModel) -> PricingRule:
    currency = Currency.of(model.currency)
    return PricingRule(
        country=CountryCode(model.country_code),
        operation=OperationType(model.operation),
        currency=currency,
        percent_bps=model.percent_bps,
        fixed_fee=_minor(model.fixed_fee_minor, currency),
        min_fee=_minor(model.min_fee_minor, currency),
        max_fee=_minor(model.max_fee_minor, currency),
        rounding=RoundingRule(model.rounding),
    )


def rule_to_model(rule: PricingRule, *, now: datetime) -> PricingRuleModel:
    return PricingRuleModel(
        country_code=rule.country.value,
        operation=rule.operation.value,
        currency=rule.currency.code,
        percent_bps=rule.percent_bps,
        fixed_fee_minor=None if rule.fixed_fee is None else rule.fixed_fee.amount_minor,
        min_fee_minor=None if rule.min_fee is None else rule.min_fee.amount_minor,
        max_fee_minor=None if rule.max_fee is None else rule.max_fee.amount_minor,
        rounding=rule.rounding.value,
        updated_at=now,
    )


class SqlAlchemyPricingRuleRepository(PricingRuleRepository):
    """Lecture directe de ``pricing_rules`` (session propre, hors Unit of Work)."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def rule_for(
        self, country: CountryCode, operation: OperationType
    ) -> PricingRule | None:
        with self._session_factory() as session:
            model = session.get(PricingRuleModel, (country.value, operation.value))
            return rule_to_domain(model) if model is not None else None


class SqlAlchemyPricingEditor:
    """CRUD back-office de la grille tarifaire. Écrit hors Unit of Work applicative."""

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory

    def get(
        self, country: CountryCode, operation: OperationType
    ) -> PricingRule | None:
        with self._session_factory() as session:
            model = session.get(PricingRuleModel, (country.value, operation.value))
            return rule_to_domain(model) if model is not None else None

    def all(self) -> list[PricingRule]:
        with self._session_factory() as session:
            stmt = select(PricingRuleModel).order_by(
                PricingRuleModel.country_code, PricingRuleModel.operation
            )
            return [rule_to_domain(m) for m in session.scalars(stmt)]

    def upsert(self, rule: PricingRule) -> None:
        with self._session_factory() as session:
            session.merge(rule_to_model(rule, now=datetime.now(UTC)))
            session.commit()

    def delete(self, country: CountryCode, operation: OperationType) -> None:
        with self._session_factory() as session:
            model = session.get(PricingRuleModel, (country.value, operation.value))
            if model is not None:
                session.delete(model)
                session.commit()


class ReadOnlyPricingEditor:
    """Éditeur refusant toute écriture — actif quand ``REFERENCE_SOURCE=static``."""

    _MSG = "Grille tarifaire en lecture seule : passez REFERENCE_SOURCE=db pour l'éditer."

    def __init__(self, repository: InMemoryPricingRuleRepository) -> None:
        self._repository = repository

    def get(
        self, country: CountryCode, operation: OperationType
    ) -> PricingRule | None:
        return self._repository.rule_for(country, operation)

    def all(self) -> list[PricingRule]:
        return self._repository.all()

    def upsert(self, rule: PricingRule) -> None:
        raise InvalidAccountState(self._MSG)

    def delete(self, country: CountryCode, operation: OperationType) -> None:
        raise InvalidAccountState(self._MSG)


def seed_pricing(session_factory: sessionmaker[Session]) -> int:
    """Charge / met à jour le jeu tarifaire par défaut en base. Idempotent."""
    now = datetime.now(UTC)
    written = 0
    with session_factory() as session:
        for rule in _default_rules():
            session.merge(rule_to_model(rule, now=now))
            written += 1
        session.commit()
    return written


__all__ = [
    "ReadOnlyPricingEditor",
    "SqlAlchemyPricingEditor",
    "SqlAlchemyPricingRuleRepository",
    "build_pricing_repository",
    "rule_to_domain",
    "rule_to_model",
    "seed_pricing",
]
