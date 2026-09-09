"""Agrégat ``Card`` — une carte virtuelle adossée à un portefeuille (BE-055).

La carte ne « détient » pas d'argent : une autorisation **réserve** des fonds sur le
portefeuille (``wallet.reserve``), la capture les consomme (``settle_reservation`` +
``LedgerTransaction`` via ``CARD_SCHEME_SUSPENSE``). Le vrai PAN n'est jamais stocké :
seul un ``pan_token`` opaque fourni par l'émetteur, plus les 4 derniers chiffres.

Invariants : plafonds jour/mois positifs ; une carte ``CLOSED`` ne redevient jamais
active ; les montants sont dans la devise de la carte et strictement positifs.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from flash.domain.card.events import (
    CardClosed,
    CardFrozen,
    CardIssued,
    CardLimitsChanged,
    CardSensitiveViewed,
    CardUnfrozen,
)
from flash.domain.shared.errors import (
    CardLimitReached,
    CardNotActive,
    ChannelDisabled,
    InvalidAccountState,
    InvalidInput,
)
from flash.domain.shared.events import EventRecorder
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import Currency, Money


class CardNetwork(StrEnum):
    VISA = "VISA"
    MASTERCARD = "MASTERCARD"


class CardStatus(StrEnum):
    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"
    CLOSED = "CLOSED"


class CardChannel(StrEnum):
    ECOM = "ECOM"  # paiement en ligne
    CONTACTLESS = "CONTACTLESS"  # sans contact
    ATM = "ATM"  # retrait distributeur


_ALL_CHANNELS: frozenset[CardChannel] = frozenset(CardChannel)


class Card(EventRecorder):
    def __init__(
        self,
        *,
        id: EntityId,
        wallet_id: EntityId,
        user_id: EntityId,
        currency: Currency,
        network: CardNetwork,
        pan_token: str,
        last4: str,
        expiry_month: int,
        expiry_year: int,
        daily_limit: Money,
        monthly_limit: Money,
        created_at: datetime,
        channels: frozenset[CardChannel] = _ALL_CHANNELS,
        status: CardStatus = CardStatus.ACTIVE,
    ) -> None:
        super().__init__()
        if len(last4) != 4 or not last4.isdigit():
            raise InvalidInput("Les 4 derniers chiffres sont invalides.")
        if not 1 <= expiry_month <= 12:
            raise InvalidInput("Mois d'expiration invalide.")
        for label, money in (("daily_limit", daily_limit), ("monthly_limit", monthly_limit)):
            if money.currency != currency:
                raise InvalidInput(f"{label} n'est pas dans la devise de la carte.")
            if not money.is_positive:
                raise InvalidInput(f"{label} doit être strictement positif.")
        if monthly_limit < daily_limit:
            raise InvalidInput("Le plafond mensuel ne peut pas être inférieur au plafond jour.")
        if not channels:
            raise InvalidInput("Au moins un canal doit être autorisé.")
        self.id = id
        self.wallet_id = wallet_id
        self.user_id = user_id
        self.currency = currency
        self.network = network
        self.pan_token = pan_token
        self.last4 = last4
        self.expiry_month = expiry_month
        self.expiry_year = expiry_year
        self.daily_limit = daily_limit
        self.monthly_limit = monthly_limit
        self.channels = frozenset(channels)
        self.created_at = created_at
        self.status = status

    # ---------------------------------------------------------------- fabrique
    @classmethod
    def issue(
        cls,
        *,
        card_id: EntityId,
        wallet_id: EntityId,
        user_id: EntityId,
        currency: Currency,
        network: CardNetwork,
        pan_token: str,
        last4: str,
        expiry_month: int,
        expiry_year: int,
        daily_limit: Money,
        monthly_limit: Money,
        now: datetime,
        channels: frozenset[CardChannel] = _ALL_CHANNELS,
    ) -> Card:
        card = cls(
            id=card_id,
            wallet_id=wallet_id,
            user_id=user_id,
            currency=currency,
            network=network,
            pan_token=pan_token,
            last4=last4,
            expiry_month=expiry_month,
            expiry_year=expiry_year,
            daily_limit=daily_limit,
            monthly_limit=monthly_limit,
            created_at=now,
            channels=channels,
        )
        card.record_event(
            CardIssued(
                occurred_at=now,
                aggregate_id=str(card_id),
                user_id=str(user_id),
                wallet_id=str(wallet_id),
                card_id=str(card_id),
                network=network.value,
                last4=last4,
            )
        )
        return card

    # ---------------------------------------------------------------- lecture
    @property
    def is_active(self) -> bool:
        return self.status is CardStatus.ACTIVE

    @property
    def masked_pan(self) -> str:
        return f"**** **** **** {self.last4}"

    # --------------------------------------------------------------- statut
    def freeze(self, reason: str, now: datetime) -> None:
        if self.status is CardStatus.CLOSED:
            raise InvalidAccountState("Cette carte est clôturée.")
        if self.status is CardStatus.FROZEN:
            return
        self.status = CardStatus.FROZEN
        self.record_event(
            CardFrozen(
                occurred_at=now,
                aggregate_id=str(self.id),
                user_id=str(self.user_id),
                card_id=str(self.id),
                reason=reason,
            )
        )

    def unfreeze(self, now: datetime) -> None:
        if self.status is CardStatus.CLOSED:
            raise InvalidAccountState("Cette carte est clôturée.")
        if self.status is CardStatus.ACTIVE:
            return
        self.status = CardStatus.ACTIVE
        self.record_event(
            CardUnfrozen(
                occurred_at=now,
                aggregate_id=str(self.id),
                user_id=str(self.user_id),
                card_id=str(self.id),
            )
        )

    def close(self, now: datetime) -> None:
        if self.status is CardStatus.CLOSED:
            return
        self.status = CardStatus.CLOSED
        self.record_event(
            CardClosed(
                occurred_at=now,
                aggregate_id=str(self.id),
                user_id=str(self.user_id),
                card_id=str(self.id),
            )
        )

    def set_limits(self, *, daily: Money, monthly: Money, now: datetime) -> None:
        if self.status is CardStatus.CLOSED:
            raise InvalidAccountState("Cette carte est clôturée.")
        for label, money in (("daily", daily), ("monthly", monthly)):
            if money.currency != self.currency:
                raise InvalidInput(f"Plafond {label} dans une autre devise.")
            if not money.is_positive:
                raise InvalidInput(f"Le plafond {label} doit être strictement positif.")
        if monthly < daily:
            raise InvalidInput("Le plafond mensuel ne peut pas être inférieur au plafond jour.")
        self.daily_limit = daily
        self.monthly_limit = monthly
        self.record_event(
            CardLimitsChanged(
                occurred_at=now,
                aggregate_id=str(self.id),
                user_id=str(self.user_id),
                card_id=str(self.id),
                daily_limit_minor=daily.amount_minor,
                monthly_limit_minor=monthly.amount_minor,
            )
        )

    def record_sensitive_view(self, now: datetime) -> None:
        if self.status is CardStatus.CLOSED:
            raise InvalidAccountState("Cette carte est clôturée.")
        self.record_event(
            CardSensitiveViewed(
                occurred_at=now,
                aggregate_id=str(self.id),
                user_id=str(self.user_id),
                card_id=str(self.id),
            )
        )

    # -------------------------------------------------------------- autorisation
    def ensure_can_authorize(
        self, *, amount: Money, channel: CardChannel, spent_today: Money, spent_month: Money
    ) -> None:
        """Lève l'erreur de domaine correspondante si l'autorisation doit être refusée."""
        if amount.currency != self.currency:
            raise InvalidInput("Devise de l'autorisation différente de celle de la carte.")
        if not amount.is_positive:
            raise InvalidInput("Le montant doit être strictement positif.")
        if self.status is not CardStatus.ACTIVE:
            raise CardNotActive()
        if channel not in self.channels:
            raise ChannelDisabled(channel=channel.value)
        if spent_today + amount > self.daily_limit:
            raise CardLimitReached(
                scope="daily",
                limit_minor=self.daily_limit.amount_minor,
                spent_minor=spent_today.amount_minor,
            )
        if spent_month + amount > self.monthly_limit:
            raise CardLimitReached(
                scope="monthly",
                limit_minor=self.monthly_limit.amount_minor,
                spent_minor=spent_month.amount_minor,
            )

    def __repr__(self) -> str:
        return (
            f"Card(id={self.id!s}, {self.network.value}, {self.masked_pan}, "
            f"status={self.status.value})"
        )


__all__ = ["Card", "CardChannel", "CardNetwork", "CardStatus"]
