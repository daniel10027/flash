"""Tests de l'agrégat ``CardAuthorization`` (BE-057)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from flash.domain.card.authorization import CardAuthorization, CardAuthorizationStatus
from flash.domain.card.card import CardChannel
from flash.domain.shared.errors import InvalidAccountState, InvalidInput
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import XOF, Money

T0 = datetime(2026, 1, 1, tzinfo=UTC)
AUTH = EntityId(UUID(int=1))
CARD = EntityId(UUID(int=2))
WALLET = EntityId(UUID(int=3))
USER = EntityId(UUID(int=4))
TXN = EntityId(UUID(int=9))


def xof(n: int) -> Money:
    return Money(n, XOF)


def _authorized(amount: int = 20_000) -> CardAuthorization:
    return CardAuthorization.authorize(
        auth_id=AUTH,
        card_id=CARD,
        wallet_id=WALLET,
        user_id=USER,
        authorization_id="auth-ext-0001",
        amount=xof(amount),
        channel=CardChannel.ECOM,
        now=T0,
        merchant_name="Boutique",
    )


class TestFactories:
    def test_authorize(self) -> None:
        auth = _authorized()
        assert auth.status is CardAuthorizationStatus.AUTHORIZED
        assert auth.is_open and auth.counts_towards_spend
        assert [e.name for e in auth.pull_events()] == ["CardPaymentAuthorized"]

    def test_declined(self) -> None:
        auth = CardAuthorization.declined(
            auth_id=AUTH,
            card_id=CARD,
            wallet_id=WALLET,
            user_id=USER,
            authorization_id="auth-ext-0002",
            amount=xof(5_000),
            channel=CardChannel.ATM,
            reason="CARD_LIMIT_REACHED",
            now=T0,
        )
        assert auth.status is CardAuthorizationStatus.DECLINED
        assert not auth.counts_towards_spend
        assert auth.decline_reason == "CARD_LIMIT_REACHED"
        assert [e.name for e in auth.pull_events()] == ["CardPaymentDeclined"]


class TestTransitions:
    def test_capture_full(self) -> None:
        auth = _authorized()
        auth.pull_events()
        auth.capture(amount=xof(20_000), ledger_transaction_id=TXN, now=T0)
        assert auth.status is CardAuthorizationStatus.CAPTURED
        assert auth.captured_minor == 20_000
        assert auth.ledger_transaction_id == TXN
        assert [e.name for e in auth.pull_events()] == ["CardPaymentCaptured"]

    def test_capture_partial(self) -> None:
        auth = _authorized()
        auth.capture(amount=xof(12_000), ledger_transaction_id=TXN, now=T0)
        assert auth.captured_minor == 12_000

    def test_capture_more_than_authorized_rejected(self) -> None:
        auth = _authorized()
        with pytest.raises(InvalidInput):
            auth.capture(amount=xof(20_001), ledger_transaction_id=TXN, now=T0)

    def test_reverse(self) -> None:
        auth = _authorized()
        auth.pull_events()
        auth.reverse(T0)
        assert auth.status is CardAuthorizationStatus.REVERSED
        assert [e.name for e in auth.pull_events()] == ["CardAuthorizationReversed"]

    def test_capture_after_reverse_rejected(self) -> None:
        auth = _authorized()
        auth.reverse(T0)
        with pytest.raises(InvalidAccountState):
            auth.capture(amount=xof(1), ledger_transaction_id=TXN, now=T0)
        with pytest.raises(InvalidAccountState):
            auth.reverse(T0)

    def test_refund_only_after_capture(self) -> None:
        auth = _authorized()
        with pytest.raises(InvalidAccountState):
            auth.refund(ledger_transaction_id=TXN, now=T0)
        auth.capture(amount=xof(20_000), ledger_transaction_id=TXN, now=T0)
        auth.pull_events()
        refunded = auth.refund(ledger_transaction_id=EntityId(UUID(int=10)), now=T0)
        assert refunded == xof(20_000)
        assert auth.status is CardAuthorizationStatus.REFUNDED
        assert [e.name for e in auth.pull_events()] == ["CardPaymentRefunded"]
