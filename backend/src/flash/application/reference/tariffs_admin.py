"""CRUD back-office de la grille tarifaire et des plafonds (reste de BE-062).

Mêmes garanties que le CRUD référentiel : rôle ``admin`` / ``compliance``, chaque
mutation **tracée** dans le registre d'audit chaîné (qui / quoi / quand / avant → après)
*avant* de renvoyer. Les règles vivent en base (``pricing_rules`` / ``limit_rules``) et
sont relues directement à chaque opération monétaire.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flash.domain.audit.ports import AuditLog
from flash.domain.identity.kyc import KycTier
from flash.domain.limits.limits import LimitRule, LimitRuleEditor
from flash.domain.pricing.pricing import PricingRule, PricingRuleEditor, RoundingRule
from flash.domain.shared.errors import InvalidInput
from flash.domain.shared.identifiers import CountryCode
from flash.domain.shared.money import Currency, Money
from flash.domain.shared.operations import OperationType
from flash.domain.shared.ports import Clock

_RESOURCE_PRICING = "pricing_rule"
_RESOURCE_LIMIT = "limit_rule"


def _country_code(raw: str) -> CountryCode:
    try:
        return CountryCode(raw.upper())
    except ValueError as exc:
        raise InvalidInput("Code pays invalide.") from exc


def _operation(raw: str) -> OperationType:
    try:
        return OperationType(raw.upper())
    except ValueError as exc:
        raise InvalidInput(f"Opération inconnue : {raw!r}.") from exc


def _currency(raw: str) -> Currency:
    try:
        return Currency.of(raw.upper())
    except ValueError as exc:
        raise InvalidInput(str(exc)) from exc


def _tier(raw: int) -> KycTier:
    try:
        return KycTier(raw)
    except ValueError as exc:
        raise InvalidInput("Palier KYC hors bornes (0 à 2).") from exc


def _money(value: int | None, currency: Currency, *, field: str) -> Money | None:
    if value is None:
        return None
    if value < 0:
        raise InvalidInput(f"`{field}` ne peut pas être négatif.")
    return Money(value, currency)


# ============================================================== vues
@dataclass(frozen=True, slots=True)
class PricingRuleView:
    country: str
    operation: str
    currency: str
    percent_bps: int
    fixed_fee_minor: int | None
    min_fee_minor: int | None
    max_fee_minor: int | None
    rounding: str

    @classmethod
    def of(cls, rule: PricingRule) -> PricingRuleView:
        return cls(
            country=rule.country.value,
            operation=rule.operation.value,
            currency=rule.currency.code,
            percent_bps=rule.percent_bps,
            fixed_fee_minor=None if rule.fixed_fee is None else rule.fixed_fee.amount_minor,
            min_fee_minor=None if rule.min_fee is None else rule.min_fee.amount_minor,
            max_fee_minor=None if rule.max_fee is None else rule.max_fee.amount_minor,
            rounding=rule.rounding.value,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "country": self.country,
            "operation": self.operation,
            "currency": self.currency,
            "percent_bps": self.percent_bps,
            "fixed_fee_minor": self.fixed_fee_minor,
            "min_fee_minor": self.min_fee_minor,
            "max_fee_minor": self.max_fee_minor,
            "rounding": self.rounding,
        }


@dataclass(frozen=True, slots=True)
class LimitRuleView:
    country: str
    kyc_tier: int
    operation: str
    currency: str
    per_tx_minor: int | None
    daily_minor: int | None
    monthly_minor: int | None
    balance_max_minor: int | None

    @classmethod
    def of(cls, rule: LimitRule) -> LimitRuleView:
        def _v(m: Money | None) -> int | None:
            return None if m is None else m.amount_minor

        anchor = rule.per_tx or rule.daily or rule.monthly or rule.balance_max
        return cls(
            country=rule.country.value,
            kyc_tier=int(rule.kyc_tier),
            operation=rule.operation.value,
            currency=anchor.currency.code if anchor is not None else "",
            per_tx_minor=_v(rule.per_tx),
            daily_minor=_v(rule.daily),
            monthly_minor=_v(rule.monthly),
            balance_max_minor=_v(rule.balance_max),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "country": self.country,
            "kyc_tier": self.kyc_tier,
            "operation": self.operation,
            "currency": self.currency,
            "per_tx_minor": self.per_tx_minor,
            "daily_minor": self.daily_minor,
            "monthly_minor": self.monthly_minor,
            "balance_max_minor": self.balance_max_minor,
        }


def _pricing_state(rule: PricingRule) -> dict[str, Any]:
    return PricingRuleView.of(rule).to_dict()


def _limit_state(rule: LimitRule) -> dict[str, Any]:
    return LimitRuleView.of(rule).to_dict()


# ============================================================== grille tarifaire
@dataclass(frozen=True, slots=True)
class UpsertPricingRuleCommand:
    actor: str
    role: str
    country: str
    operation: str
    currency: str
    percent_bps: int = 0
    fixed_fee_minor: int | None = None
    min_fee_minor: int | None = None
    max_fee_minor: int | None = None
    rounding: str = "HALF_UP"


@dataclass(frozen=True, slots=True)
class DeletePricingRuleCommand:
    actor: str
    role: str
    country: str
    operation: str


class ListPricingRules:
    def __init__(self, *, editor: PricingRuleEditor) -> None:
        self._editor = editor

    def execute(self) -> list[PricingRuleView]:
        return [PricingRuleView.of(r) for r in self._editor.all()]


class UpsertPricingRule:
    def __init__(
        self, *, editor: PricingRuleEditor, audit: AuditLog, clock: Clock
    ) -> None:
        self._editor = editor
        self._audit = audit
        self._clock = clock

    def execute(self, command: UpsertPricingRuleCommand) -> PricingRuleView:
        country = _country_code(command.country)
        operation = _operation(command.operation)
        currency = _currency(command.currency)
        try:
            rounding = RoundingRule(command.rounding.upper())
        except ValueError as exc:
            raise InvalidInput(f"Arrondi inconnu : {command.rounding!r}.") from exc
        try:
            rule = PricingRule(
                country=country,
                operation=operation,
                currency=currency,
                percent_bps=command.percent_bps,
                fixed_fee=_money(command.fixed_fee_minor, currency, field="fixed_fee_minor"),
                min_fee=_money(command.min_fee_minor, currency, field="min_fee_minor"),
                max_fee=_money(command.max_fee_minor, currency, field="max_fee_minor"),
                rounding=rounding,
            )
        except ValueError as exc:
            raise InvalidInput(str(exc)) from exc

        existing = self._editor.get(country, operation)
        self._editor.upsert(rule)
        self._audit.append(
            actor=command.actor,
            role=command.role,
            action="pricing_rule.update" if existing else "pricing_rule.create",
            resource_type=_RESOURCE_PRICING,
            resource_id=f"{country.value}:{operation.value}",
            before=_pricing_state(existing) if existing else None,
            after=_pricing_state(rule),
            now=self._clock.now(),
        )
        return PricingRuleView.of(self._editor.get(country, operation) or rule)


class DeletePricingRule:
    def __init__(
        self, *, editor: PricingRuleEditor, audit: AuditLog, clock: Clock
    ) -> None:
        self._editor = editor
        self._audit = audit
        self._clock = clock

    def execute(self, command: DeletePricingRuleCommand) -> None:
        country = _country_code(command.country)
        operation = _operation(command.operation)
        existing = self._editor.get(country, operation)
        if existing is None:
            raise InvalidInput("Règle tarifaire introuvable.")
        self._editor.delete(country, operation)
        self._audit.append(
            actor=command.actor,
            role=command.role,
            action="pricing_rule.delete",
            resource_type=_RESOURCE_PRICING,
            resource_id=f"{country.value}:{operation.value}",
            before=_pricing_state(existing),
            after=None,
            now=self._clock.now(),
        )


# ============================================================== plafonds
@dataclass(frozen=True, slots=True)
class UpsertLimitRuleCommand:
    actor: str
    role: str
    country: str
    kyc_tier: int
    operation: str
    currency: str
    per_tx_minor: int | None = None
    daily_minor: int | None = None
    monthly_minor: int | None = None
    balance_max_minor: int | None = None


@dataclass(frozen=True, slots=True)
class DeleteLimitRuleCommand:
    actor: str
    role: str
    country: str
    kyc_tier: int
    operation: str


class ListLimitRules:
    def __init__(self, *, editor: LimitRuleEditor) -> None:
        self._editor = editor

    def execute(self) -> list[LimitRuleView]:
        return [LimitRuleView.of(r) for r in self._editor.all()]


class UpsertLimitRule:
    def __init__(self, *, editor: LimitRuleEditor, audit: AuditLog, clock: Clock) -> None:
        self._editor = editor
        self._audit = audit
        self._clock = clock

    def execute(self, command: UpsertLimitRuleCommand) -> LimitRuleView:
        country = _country_code(command.country)
        tier = _tier(command.kyc_tier)
        operation = _operation(command.operation)
        currency = _currency(command.currency)
        caps = (
            _money(command.per_tx_minor, currency, field="per_tx_minor"),
            _money(command.daily_minor, currency, field="daily_minor"),
            _money(command.monthly_minor, currency, field="monthly_minor"),
            _money(command.balance_max_minor, currency, field="balance_max_minor"),
        )
        if all(cap is None for cap in caps):
            raise InvalidInput(
                "Fixez au moins un plafond (per_tx / daily / monthly / balance_max)."
            )
        try:
            rule = LimitRule(
                country=country,
                kyc_tier=tier,
                operation=operation,
                per_tx=caps[0],
                daily=caps[1],
                monthly=caps[2],
                balance_max=caps[3],
            )
        except ValueError as exc:  # pragma: no cover - montants déjà validés par _money
            raise InvalidInput(str(exc)) from exc

        existing = self._editor.get(country, tier, operation)
        self._editor.upsert(rule)
        self._audit.append(
            actor=command.actor,
            role=command.role,
            action="limit_rule.update" if existing else "limit_rule.create",
            resource_type=_RESOURCE_LIMIT,
            resource_id=f"{country.value}:{int(tier)}:{operation.value}",
            before=_limit_state(existing) if existing else None,
            after=_limit_state(rule),
            now=self._clock.now(),
        )
        return LimitRuleView.of(self._editor.get(country, tier, operation) or rule)


class DeleteLimitRule:
    def __init__(self, *, editor: LimitRuleEditor, audit: AuditLog, clock: Clock) -> None:
        self._editor = editor
        self._audit = audit
        self._clock = clock

    def execute(self, command: DeleteLimitRuleCommand) -> None:
        country = _country_code(command.country)
        tier = _tier(command.kyc_tier)
        operation = _operation(command.operation)
        existing = self._editor.get(country, tier, operation)
        if existing is None:
            raise InvalidInput("Règle de plafond introuvable.")
        self._editor.delete(country, tier, operation)
        self._audit.append(
            actor=command.actor,
            role=command.role,
            action="limit_rule.delete",
            resource_type=_RESOURCE_LIMIT,
            resource_id=f"{country.value}:{int(tier)}:{operation.value}",
            before=_limit_state(existing),
            after=None,
            now=self._clock.now(),
        )


__all__ = [
    "DeleteLimitRule",
    "DeleteLimitRuleCommand",
    "DeletePricingRule",
    "DeletePricingRuleCommand",
    "LimitRuleView",
    "ListLimitRules",
    "ListPricingRules",
    "PricingRuleView",
    "UpsertLimitRule",
    "UpsertLimitRuleCommand",
    "UpsertPricingRule",
    "UpsertPricingRuleCommand",
]
