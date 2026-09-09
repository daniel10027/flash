"""Tests de l'agrégat ``Card`` (BE-055)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from flash.domain.card.card import Card, CardChannel, CardNetwork, CardStatus
from flash.domain.shared.errors import (
    CardLimitReached,
    CardNotActive,
    ChannelDisabled,
    InvalidAccountState,
    InvalidInput,
)
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import XOF, Currency, Money

T0 = datetime(2026, 1, 1, tzinfo=UTC)
CARD = EntityId(UUID(int=1))
WALLET = EntityId(UUID(int=2))
USER = EntityId(UUID(int=3))


def xof(n: int) -> Money:
    return Money(n, XOF)


def new_card(**kw: object) -> Card:
    params: dict[str, object] = {
        "card_id": CARD,
        "wallet_id": WALLET,
        "user_id": USER,
        "currency": XOF,
        "network": CardNetwork.VISA,
        "pan_token": "tok_abcdef0123456789",
        "last4": "4242",
        "expiry_month": 12,
        "expiry_year": 2030,
        "daily_limit": xof(500_000),
        "monthly_limit": xof(5_000_000),
        "now": T0,
    }
    params.update(kw)
    return Card.issue(**params)  # type: ignore[arg-type]


class TestIssue:
    def test_issue_is_active_and_records_event(self) -> None:
        card = new_card()
        assert card.is_active
        assert card.masked_pan == "**** **** **** 4242"
        assert card.channels == frozenset(CardChannel)
        assert [e.name for e in card.pull_events()] == ["CardIssued"]

    def test_bad_last4_rejected(self) -> None:
        with pytest.raises(InvalidInput, match="4 derniers"):
            new_card(last4="12x")

    def test_bad_month_rejected(self) -> None:
        with pytest.raises(InvalidInput, match=r"[Mm]ois"):
            new_card(expiry_month=13)

    def test_limit_currency_mismatch_rejected(self) -> None:
        with pytest.raises(InvalidInput, match="devise"):
            new_card(daily_limit=Money(1_000, Currency.of("EUR")))

    def test_non_positive_limit_rejected(self) -> None:
        with pytest.raises(InvalidInput, match="strictement positif"):
            new_card(daily_limit=xof(0))

    def test_monthly_below_daily_rejected(self) -> None:
        with pytest.raises(InvalidInput, match="mensuel"):
            new_card(daily_limit=xof(600_000), monthly_limit=xof(500_000))

    def test_empty_channels_rejected(self) -> None:
        with pytest.raises(InvalidInput, match="canal"):
            new_card(channels=frozenset())


class TestStatus:
    def test_freeze_unfreeze_cycle(self) -> None:
        card = new_card()
        card.pull_events()
        card.freeze("perte", T0)
        assert card.status is CardStatus.FROZEN
        assert [e.name for e in card.pull_events()] == ["CardFrozen"]
        card.freeze("perte", T0)  # idempotent
        assert card.pull_events() == []
        card.unfreeze(T0)
        assert card.status is CardStatus.ACTIVE
        assert [e.name for e in card.pull_events()] == ["CardUnfrozen"]
        card.unfreeze(T0)  # idempotent
        assert card.pull_events() == []

    def test_close_is_terminal(self) -> None:
        card = new_card()
        card.close(T0)
        assert card.status is CardStatus.CLOSED
        for action in (
            lambda: card.freeze("x", T0),
            lambda: card.unfreeze(T0),
            lambda: card.set_limits(daily=xof(1), monthly=xof(1), now=T0),
            lambda: card.record_sensitive_view(T0),
        ):
            with pytest.raises(InvalidAccountState):
                action()
        card.close(T0)  # re-close no-op
        assert card.pull_events()[-1].name == "CardClosed"

    def test_set_limits(self) -> None:
        card = new_card()
        card.pull_events()
        card.set_limits(daily=xof(200_000), monthly=xof(2_000_000), now=T0)
        assert card.daily_limit == xof(200_000)
        assert [e.name for e in card.pull_events()] == ["CardLimitsChanged"]

    def test_set_limits_validation(self) -> None:
        card = new_card()
        with pytest.raises(InvalidInput, match="strictement positif"):
            card.set_limits(daily=xof(0), monthly=xof(10), now=T0)
        with pytest.raises(InvalidInput, match="strictement positif"):
            card.set_limits(daily=xof(10), monthly=xof(0), now=T0)
        with pytest.raises(InvalidInput, match="devise"):
            card.set_limits(daily=Money(10, Currency.of("EUR")), monthly=xof(10), now=T0)
        with pytest.raises(InvalidInput, match="mensuel"):
            card.set_limits(daily=xof(10), monthly=xof(5), now=T0)

    def test_record_sensitive_view_emits_audit_event(self) -> None:
        card = new_card()
        card.pull_events()
        card.record_sensitive_view(T0)
        assert [e.name for e in card.pull_events()] == ["CardSensitiveViewed"]


class TestAuthorizationGuard:
    def test_ok_within_limits(self) -> None:
        new_card().ensure_can_authorize(
            amount=xof(10_000),
            channel=CardChannel.ECOM,
            spent_today=xof(0),
            spent_month=xof(0),
        )

    def test_frozen_card_rejected(self) -> None:
        card = new_card()
        card.freeze("x", T0)
        with pytest.raises(CardNotActive):
            card.ensure_can_authorize(
                amount=xof(10), channel=CardChannel.ECOM, spent_today=xof(0), spent_month=xof(0)
            )

    def test_disabled_channel_rejected(self) -> None:
        card = new_card(channels=frozenset({CardChannel.ECOM}))
        with pytest.raises(ChannelDisabled):
            card.ensure_can_authorize(
                amount=xof(10),
                channel=CardChannel.ATM,
                spent_today=xof(0),
                spent_month=xof(0),
            )

    def test_daily_limit_rejected(self) -> None:
        card = new_card(daily_limit=xof(50_000))
        with pytest.raises(CardLimitReached) as exc:
            card.ensure_can_authorize(
                amount=xof(10_000),
                channel=CardChannel.ECOM,
                spent_today=xof(45_000),
                spent_month=xof(45_000),
            )
        assert exc.value.details["scope"] == "daily"

    def test_monthly_limit_rejected(self) -> None:
        card = new_card(daily_limit=xof(100_000), monthly_limit=xof(100_000))
        with pytest.raises(CardLimitReached) as exc:
            card.ensure_can_authorize(
                amount=xof(20_000),
                channel=CardChannel.ECOM,
                spent_today=xof(0),
                spent_month=xof(90_000),
            )
        assert exc.value.details["scope"] == "monthly"

    def test_bad_amount_rejected(self) -> None:
        card = new_card()
        with pytest.raises(InvalidInput):
            card.ensure_can_authorize(
                amount=xof(0), channel=CardChannel.ECOM, spent_today=xof(0), spent_month=xof(0)
            )
        with pytest.raises(InvalidInput):
            card.ensure_can_authorize(
                amount=Money(10, Currency.of("EUR")),
                channel=CardChannel.ECOM,
                spent_today=xof(0),
                spent_month=xof(0),
            )

    def test_repr(self) -> None:
        assert "4242" in repr(new_card()) and "VISA" in repr(new_card())
