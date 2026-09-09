"""Intégration : dépôts SQLAlchemy des agrégats ``Card`` et ``CardAuthorization``."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session, sessionmaker

from flash.domain.card.authorization import CardAuthorization, CardAuthorizationStatus
from flash.domain.card.card import Card, CardChannel, CardNetwork
from flash.domain.identity.user import User
from flash.domain.shared.identifiers import CountryCode, EntityId, Msisdn
from flash.domain.shared.money import XOF, Money
from flash.domain.wallet.wallet import Wallet
from flash.infrastructure.db.uow import SqlAlchemyUnitOfWork
from flash.infrastructure.ids import uuid7
from tests.support.fakes import FixedClock

pytestmark = pytest.mark.integration

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _user(msisdn: str) -> User:
    user = User.register(
        user_id=EntityId(str(uuid7())),
        country=CountryCode("CI"),
        msisdn=Msisdn(msisdn),
        pin_hash="hashed:1397",
        now=T0,
    )
    user.activate(T0)
    return user


def test_card_and_authorization_roundtrip(session_factory: sessionmaker[Session]) -> None:
    clock = FixedClock(T0)
    user = _user("+2250700000501")
    wallet = Wallet.open(
        wallet_id=EntityId(str(uuid7())), user_id=user.id, currency=XOF, now=T0
    )
    wallet.credit(Money(200_000, XOF), T0)
    card_id = EntityId(str(uuid7()))
    auth_id = EntityId(str(uuid7()))

    with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
        uow.users.add(user)
        uow.wallets.add(wallet)
        card = Card.issue(
            card_id=card_id,
            wallet_id=EntityId(str(wallet.id)),
            user_id=user.id,
            currency=XOF,
            network=CardNetwork.MASTERCARD,
            pan_token="tok_integration_0001",
            last4="4242",
            expiry_month=6,
            expiry_year=2031,
            daily_limit=Money(300_000, XOF),
            monthly_limit=Money(3_000_000, XOF),
            now=T0,
            channels=frozenset({CardChannel.ECOM, CardChannel.CONTACTLESS}),
        )
        uow.cards.add(card)
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
        card = uow.cards.get(card_id)
        assert card is not None
        assert card.network is CardNetwork.MASTERCARD
        assert card.channels == frozenset({CardChannel.ECOM, CardChannel.CONTACTLESS})
        assert card.daily_limit == Money(300_000, XOF)
        assert uow.cards.get_by_pan_token("tok_integration_0001") is not None
        assert [c.id for c in uow.cards.list_for_user(user.id)] == [card_id]

    # autorisation puis capture
    with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
        auth = CardAuthorization.authorize(
            auth_id=auth_id,
            card_id=card_id,
            wallet_id=EntityId(str(wallet.id)),
            user_id=user.id,
            authorization_id="ext-auth-int-1",
            amount=Money(40_000, XOF),
            channel=CardChannel.ECOM,
            now=T0,
            merchant_name="Boutique",
        )
        uow.card_authorizations.add(auth)
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
        spent = uow.card_authorizations.total_spent_since(card_id, T0 - timedelta(hours=1))
        assert spent == Money(40_000, XOF)
        auth = uow.card_authorizations.get_for_update_by_authorization_id("ext-auth-int-1")
        auth.capture(
            amount=Money(40_000, XOF),
            ledger_transaction_id=EntityId(str(uuid7())),
            now=T0,
        )
        uow.card_authorizations.save(auth)
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
        [resolved] = uow.card_authorizations.list_resolved()
        assert resolved.status is CardAuthorizationStatus.CAPTURED
        assert resolved.captured_minor == 40_000
        # une capture ne compte plus dans les "dépenses en cours" ? si : AUTHORIZED+CAPTURED
        assert uow.card_authorizations.total_spent_since(
            card_id, T0 - timedelta(hours=1)
        ) == Money(40_000, XOF)
        assert [a.authorization_id for a in uow.card_authorizations.list_for_card(card_id)] == [
            "ext-auth-int-1"
        ]
