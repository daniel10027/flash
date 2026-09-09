"""Agrégat ``CardAuthorization`` — le cycle de vie d'une autorisation carte (BE-057).

``AUTHORIZED`` (fonds réservés sur le portefeuille) → ``CAPTURED`` (fonds consommés,
écriture ``CARD_CAPTURE``) ou ``REVERSED`` (réserve rendue). Après capture, ``REFUNDED``
(écriture ``CARD_REFUND``). ``DECLINED`` : refusée d'emblée, sans toucher au portefeuille.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from flash.domain.card.card import CardChannel
from flash.domain.card.events import (
    CardAuthorizationReversed,
    CardPaymentAuthorized,
    CardPaymentCaptured,
    CardPaymentDeclined,
    CardPaymentRefunded,
)
from flash.domain.shared.errors import InvalidAccountState, InvalidInput
from flash.domain.shared.events import EventRecorder
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import Money


class CardAuthorizationStatus(StrEnum):
    AUTHORIZED = "AUTHORIZED"
    CAPTURED = "CAPTURED"
    REVERSED = "REVERSED"
    REFUNDED = "REFUNDED"
    DECLINED = "DECLINED"


class CardAuthorization(EventRecorder):
    def __init__(
        self,
        *,
        id: EntityId,
        card_id: EntityId,
        wallet_id: EntityId,
        user_id: EntityId,
        authorization_id: str,
        amount: Money,
        currency_code: str,
        channel: CardChannel,
        status: CardAuthorizationStatus,
        created_at: datetime,
        merchant_name: str | None = None,
        decline_reason: str | None = None,
        resolved_at: datetime | None = None,
        captured_minor: int | None = None,
        ledger_transaction_id: EntityId | None = None,
    ) -> None:
        super().__init__()
        self.id = id
        self.card_id = card_id
        self.wallet_id = wallet_id
        self.user_id = user_id
        self.authorization_id = authorization_id
        self.amount = amount
        self.currency_code = currency_code
        self.channel = channel
        self.status = status
        self.created_at = created_at
        self.merchant_name = merchant_name
        self.decline_reason = decline_reason
        self.resolved_at = resolved_at
        self.captured_minor = captured_minor
        self.ledger_transaction_id = ledger_transaction_id

    # ---------------------------------------------------------------- fabriques
    @classmethod
    def authorize(
        cls,
        *,
        auth_id: EntityId,
        card_id: EntityId,
        wallet_id: EntityId,
        user_id: EntityId,
        authorization_id: str,
        amount: Money,
        channel: CardChannel,
        now: datetime,
        merchant_name: str | None = None,
    ) -> CardAuthorization:
        auth = cls(
            id=auth_id,
            card_id=card_id,
            wallet_id=wallet_id,
            user_id=user_id,
            authorization_id=authorization_id,
            amount=amount,
            currency_code=amount.currency.code,
            channel=channel,
            status=CardAuthorizationStatus.AUTHORIZED,
            created_at=now,
            merchant_name=merchant_name,
        )
        auth.record_event(
            CardPaymentAuthorized(
                occurred_at=now,
                aggregate_id=str(auth_id),
                user_id=str(user_id),
                wallet_id=str(wallet_id),
                card_id=str(card_id),
                authorization_id=authorization_id,
                amount_minor=amount.amount_minor,
                currency=amount.currency.code,
                channel=channel.value,
                merchant_name=merchant_name,
            )
        )
        return auth

    @classmethod
    def declined(
        cls,
        *,
        auth_id: EntityId,
        card_id: EntityId,
        wallet_id: EntityId,
        user_id: EntityId,
        authorization_id: str,
        amount: Money,
        channel: CardChannel,
        reason: str,
        now: datetime,
        merchant_name: str | None = None,
    ) -> CardAuthorization:
        auth = cls(
            id=auth_id,
            card_id=card_id,
            wallet_id=wallet_id,
            user_id=user_id,
            authorization_id=authorization_id,
            amount=amount,
            currency_code=amount.currency.code,
            channel=channel,
            status=CardAuthorizationStatus.DECLINED,
            created_at=now,
            merchant_name=merchant_name,
            decline_reason=reason,
            resolved_at=now,
        )
        auth.record_event(
            CardPaymentDeclined(
                occurred_at=now,
                aggregate_id=str(auth_id),
                user_id=str(user_id),
                card_id=str(card_id),
                authorization_id=authorization_id,
                amount_minor=amount.amount_minor,
                currency=amount.currency.code,
                reason=reason,
            )
        )
        return auth

    # ---------------------------------------------------------------- lecture
    @property
    def is_open(self) -> bool:
        return self.status is CardAuthorizationStatus.AUTHORIZED

    @property
    def counts_towards_spend(self) -> bool:
        return self.status in (
            CardAuthorizationStatus.AUTHORIZED,
            CardAuthorizationStatus.CAPTURED,
        )

    # ---------------------------------------------------------------- transitions
    def capture(self, *, amount: Money, ledger_transaction_id: EntityId, now: datetime) -> None:
        if not self.is_open:
            raise InvalidAccountState("Cette autorisation n'est plus capturable.")
        if not amount.is_positive or amount > self.amount:
            raise InvalidInput("Montant de capture invalide.")
        self.status = CardAuthorizationStatus.CAPTURED
        self.captured_minor = amount.amount_minor
        self.ledger_transaction_id = ledger_transaction_id
        self.resolved_at = now
        self.record_event(
            CardPaymentCaptured(
                occurred_at=now,
                aggregate_id=str(self.id),
                user_id=str(self.user_id),
                wallet_id=str(self.wallet_id),
                card_id=str(self.card_id),
                authorization_id=self.authorization_id,
                amount_minor=amount.amount_minor,
                currency=self.currency_code,
            )
        )

    def reverse(self, now: datetime) -> None:
        if not self.is_open:
            raise InvalidAccountState("Cette autorisation n'est plus annulable.")
        self.status = CardAuthorizationStatus.REVERSED
        self.resolved_at = now
        self.record_event(
            CardAuthorizationReversed(
                occurred_at=now,
                aggregate_id=str(self.id),
                user_id=str(self.user_id),
                wallet_id=str(self.wallet_id),
                card_id=str(self.card_id),
                authorization_id=self.authorization_id,
                amount_minor=self.amount.amount_minor,
                currency=self.currency_code,
            )
        )

    def refund(self, *, ledger_transaction_id: EntityId, now: datetime) -> Money:
        if self.status is not CardAuthorizationStatus.CAPTURED:
            raise InvalidAccountState("Seule une autorisation capturée peut être remboursée.")
        refunded_minor = self.captured_minor if self.captured_minor is not None else 0
        self.status = CardAuthorizationStatus.REFUNDED
        self.ledger_transaction_id = ledger_transaction_id
        self.resolved_at = now
        refunded = self.amount.with_amount(refunded_minor)
        self.record_event(
            CardPaymentRefunded(
                occurred_at=now,
                aggregate_id=str(self.id),
                user_id=str(self.user_id),
                wallet_id=str(self.wallet_id),
                card_id=str(self.card_id),
                authorization_id=self.authorization_id,
                amount_minor=refunded_minor,
                currency=self.currency_code,
            )
        )
        return refunded


__all__ = ["CardAuthorization", "CardAuthorizationStatus"]
