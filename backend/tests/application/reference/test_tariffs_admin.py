"""Tests du CRUD back-office grille tarifaire & plafonds + traçabilité (reste de BE-062)."""

from __future__ import annotations

from uuid import UUID

import pytest

from flash.application.reference.tariffs_admin import (
    DeleteLimitRule,
    DeleteLimitRuleCommand,
    DeletePricingRule,
    DeletePricingRuleCommand,
    ListLimitRules,
    ListPricingRules,
    UpsertLimitRule,
    UpsertLimitRuleCommand,
    UpsertPricingRule,
    UpsertPricingRuleCommand,
)
from flash.domain.identity.kyc import KycTier
from flash.domain.limits.limits import (
    InMemoryLimitCounter,
    InMemoryLimitRuleRepository,
    LimitPolicy,
)
from flash.domain.pricing.pricing import (
    InMemoryPricingRuleRepository,
    PricingService,
)
from flash.domain.shared.errors import InvalidInput, LimitExceeded
from flash.domain.shared.identifiers import CountryCode, EntityId
from flash.domain.shared.money import XOF, Money
from flash.domain.shared.operations import OperationType
from tests.support.audit import InMemoryAuditLog
from tests.support.fakes import FixedClock


@pytest.fixture
def pricing() -> InMemoryPricingRuleRepository:
    return InMemoryPricingRuleRepository()


@pytest.fixture
def limits() -> InMemoryLimitRuleRepository:
    return InMemoryLimitRuleRepository()


@pytest.fixture
def audit() -> InMemoryAuditLog:
    return InMemoryAuditLog()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


class TestPricingCrud:
    def test_create_then_update_traces_before_after(
        self,
        pricing: InMemoryPricingRuleRepository,
        audit: InMemoryAuditLog,
        clock: FixedClock,
    ) -> None:
        uc = UpsertPricingRule(editor=pricing, audit=audit, clock=clock)
        uc.execute(
            UpsertPricingRuleCommand(
                actor="key:admin", role="admin", country="ci", operation="transfer",
                currency="XOF", percent_bps=80, min_fee_minor=1, rounding="UP_TO_UNIT",
            )
        )
        view = uc.execute(
            UpsertPricingRuleCommand(
                actor="key:admin", role="admin", country="CI", operation="TRANSFER",
                currency="XOF", percent_bps=95,
            )
        )
        assert view.percent_bps == 95
        entries = audit.recent()
        assert [e.action for e in entries] == ["pricing_rule.update", "pricing_rule.create"]
        assert entries[0].resource_id == "CI:TRANSFER"
        assert entries[0].before is not None and entries[0].before["percent_bps"] == 80
        assert entries[0].after is not None and entries[0].after["percent_bps"] == 95
        assert audit.verify() is True

    def test_rule_becomes_effective_for_pricing_service(
        self,
        pricing: InMemoryPricingRuleRepository,
        audit: InMemoryAuditLog,
        clock: FixedClock,
    ) -> None:
        UpsertPricingRule(editor=pricing, audit=audit, clock=clock).execute(
            UpsertPricingRuleCommand(
                actor="a", role="admin", country="CI", operation="TRANSFER",
                currency="XOF", percent_bps=100,
            )
        )
        fee = PricingService(pricing).fee_for(
            country=CountryCode("CI"),
            operation=OperationType.TRANSFER,
            amount=Money(10_000, XOF),
        )
        assert fee.total == Money(100, XOF)

    def test_delete_requires_existing(
        self,
        pricing: InMemoryPricingRuleRepository,
        audit: InMemoryAuditLog,
        clock: FixedClock,
    ) -> None:
        with pytest.raises(InvalidInput, match="introuvable"):
            DeletePricingRule(editor=pricing, audit=audit, clock=clock).execute(
                DeletePricingRuleCommand(
                    actor="a", role="admin", country="CI", operation="TRANSFER"
                )
            )

    def test_delete_traces_and_removes(
        self,
        pricing: InMemoryPricingRuleRepository,
        audit: InMemoryAuditLog,
        clock: FixedClock,
    ) -> None:
        UpsertPricingRule(editor=pricing, audit=audit, clock=clock).execute(
            UpsertPricingRuleCommand(
                actor="a", role="admin", country="CI", operation="TRANSFER",
                currency="XOF", percent_bps=80,
            )
        )
        DeletePricingRule(editor=pricing, audit=audit, clock=clock).execute(
            DeletePricingRuleCommand(
                actor="a", role="admin", country="CI", operation="TRANSFER"
            )
        )
        assert ListPricingRules(editor=pricing).execute() == []
        assert audit.recent()[0].action == "pricing_rule.delete"
        assert audit.recent()[0].after is None

    def test_invalid_operation_rejected(
        self,
        pricing: InMemoryPricingRuleRepository,
        audit: InMemoryAuditLog,
        clock: FixedClock,
    ) -> None:
        with pytest.raises(InvalidInput, match="Opération inconnue"):
            UpsertPricingRule(editor=pricing, audit=audit, clock=clock).execute(
                UpsertPricingRuleCommand(
                    actor="a", role="admin", country="CI", operation="FLYING",
                    currency="XOF",
                )
            )

    def test_min_greater_than_max_rejected(
        self,
        pricing: InMemoryPricingRuleRepository,
        audit: InMemoryAuditLog,
        clock: FixedClock,
    ) -> None:
        with pytest.raises(InvalidInput):
            UpsertPricingRule(editor=pricing, audit=audit, clock=clock).execute(
                UpsertPricingRuleCommand(
                    actor="a", role="admin", country="CI", operation="TRANSFER",
                    currency="XOF", min_fee_minor=500, max_fee_minor=100,
                )
            )

    @pytest.mark.parametrize(
        ("field", "value", "match"),
        [
            ("country", "X", "Code pays"),
            ("currency", "ZZZ", "Devise inconnue"),
            ("rounding", "SIDEWAYS", "Arrondi inconnu"),
        ],
    )
    def test_field_validation(
        self,
        pricing: InMemoryPricingRuleRepository,
        audit: InMemoryAuditLog,
        clock: FixedClock,
        field: str,
        value: str,
        match: str,
    ) -> None:
        kwargs: dict[str, str] = {
            "actor": "a",
            "role": "admin",
            "country": "CI",
            "operation": "TRANSFER",
            "currency": "XOF",
        }
        kwargs[field] = value
        with pytest.raises(InvalidInput, match=match):
            UpsertPricingRule(editor=pricing, audit=audit, clock=clock).execute(
                UpsertPricingRuleCommand(**kwargs)  # type: ignore[arg-type]
            )

    def test_negative_fee_rejected(
        self,
        pricing: InMemoryPricingRuleRepository,
        audit: InMemoryAuditLog,
        clock: FixedClock,
    ) -> None:
        with pytest.raises(InvalidInput, match="négatif"):
            UpsertPricingRule(editor=pricing, audit=audit, clock=clock).execute(
                UpsertPricingRuleCommand(
                    actor="a", role="admin", country="CI", operation="TRANSFER",
                    currency="XOF", min_fee_minor=-5,
                )
            )


class TestLimitCrud:
    def test_create_update_delete_traces(
        self,
        limits: InMemoryLimitRuleRepository,
        audit: InMemoryAuditLog,
        clock: FixedClock,
    ) -> None:
        uc = UpsertLimitRule(editor=limits, audit=audit, clock=clock)
        uc.execute(
            UpsertLimitRuleCommand(
                actor="a", role="admin", country="CI", kyc_tier=1, operation="TRANSFER",
                currency="XOF", per_tx_minor=1_000_000, balance_max_minor=2_000_000,
            )
        )
        view = uc.execute(
            UpsertLimitRuleCommand(
                actor="a", role="admin", country="CI", kyc_tier=1, operation="TRANSFER",
                currency="XOF", per_tx_minor=1_500_000,
            )
        )
        assert view.per_tx_minor == 1_500_000 and view.balance_max_minor is None
        DeleteLimitRule(editor=limits, audit=audit, clock=clock).execute(
            DeleteLimitRuleCommand(
                actor="a", role="admin", country="CI", kyc_tier=1, operation="TRANSFER"
            )
        )
        assert ListLimitRules(editor=limits).execute() == []
        assert [e.action for e in audit.recent()] == [
            "limit_rule.delete",
            "limit_rule.update",
            "limit_rule.create",
        ]
        assert audit.recent()[1].resource_id == "CI:1:TRANSFER"

    def test_rule_becomes_effective_for_limit_policy(
        self,
        limits: InMemoryLimitRuleRepository,
        audit: InMemoryAuditLog,
        clock: FixedClock,
    ) -> None:
        UpsertLimitRule(editor=limits, audit=audit, clock=clock).execute(
            UpsertLimitRuleCommand(
                actor="a", role="admin", country="CI", kyc_tier=0, operation="TRANSFER",
                currency="XOF", per_tx_minor=50_000,
            )
        )
        policy = LimitPolicy(limits, InMemoryLimitCounter())
        with pytest.raises(LimitExceeded):
            policy.check(
                user_id=EntityId(str(UUID(int=1))),
                country=CountryCode("CI"),
                kyc_tier=KycTier.TIER_0,
                operation=OperationType.TRANSFER,
                amount=Money(60_000, XOF),
            )

    def test_needs_at_least_one_cap(
        self,
        limits: InMemoryLimitRuleRepository,
        audit: InMemoryAuditLog,
        clock: FixedClock,
    ) -> None:
        with pytest.raises(InvalidInput, match="au moins un plafond"):
            UpsertLimitRule(editor=limits, audit=audit, clock=clock).execute(
                UpsertLimitRuleCommand(
                    actor="a", role="admin", country="CI", kyc_tier=1,
                    operation="TRANSFER", currency="XOF",
                )
            )

    def test_delete_unknown_rejected(
        self,
        limits: InMemoryLimitRuleRepository,
        audit: InMemoryAuditLog,
        clock: FixedClock,
    ) -> None:
        with pytest.raises(InvalidInput, match="introuvable"):
            DeleteLimitRule(editor=limits, audit=audit, clock=clock).execute(
                DeleteLimitRuleCommand(
                    actor="a", role="admin", country="CI", kyc_tier=1, operation="TRANSFER"
                )
            )

    def test_bad_tier_rejected(
        self,
        limits: InMemoryLimitRuleRepository,
        audit: InMemoryAuditLog,
        clock: FixedClock,
    ) -> None:
        with pytest.raises(InvalidInput, match="Palier KYC"):
            UpsertLimitRule(editor=limits, audit=audit, clock=clock).execute(
                UpsertLimitRuleCommand(
                    actor="a", role="admin", country="CI", kyc_tier=9,
                    operation="TRANSFER", currency="XOF", per_tx_minor=1,
                )
            )
