"""Cycle de vie d'une carte virtuelle (BE-056 / BE-058).

Émission, gel / dégel, clôture, plafonds, et révélation ponctuelle des données sensibles
(PAN / CVV) — cette dernière est auditée (``CardSensitiveViewed``) et n'est **jamais**
journalisée ni persistée.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flash.application.card.ports import CardIssuer
from flash.application.services import AppServices
from flash.application.transaction import execute_in_uow
from flash.application.unit_of_work import WorkUnitOfWork
from flash.application.use_case import Command, UseCase
from flash.domain.card.card import Card, CardChannel, CardNetwork
from flash.domain.shared.errors import InvalidInput
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import Money

_DEFAULT_DAILY_MINOR = 500_000
_DEFAULT_MONTHLY_MINOR = 5_000_000


# --------------------------------------------------------------------- vues
@dataclass(frozen=True, slots=True)
class CardView:
    card_id: str
    network: str
    masked_pan: str
    last4: str
    expiry_month: int
    expiry_year: int
    status: str
    currency: str
    daily_limit_minor: int
    monthly_limit_minor: int
    channels: list[str]
    created_at: str

    @classmethod
    def of(cls, card: Card) -> CardView:
        return cls(
            card_id=str(card.id),
            network=card.network.value,
            masked_pan=card.masked_pan,
            last4=card.last4,
            expiry_month=card.expiry_month,
            expiry_year=card.expiry_year,
            status=card.status.value,
            currency=card.currency.code,
            daily_limit_minor=card.daily_limit.amount_minor,
            monthly_limit_minor=card.monthly_limit.amount_minor,
            channels=sorted(c.value for c in card.channels),
            created_at=card.created_at.isoformat(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "card_id": self.card_id,
            "network": self.network,
            "masked_pan": self.masked_pan,
            "last4": self.last4,
            "expiry_month": self.expiry_month,
            "expiry_year": self.expiry_year,
            "status": self.status,
            "currency": self.currency,
            "daily_limit_minor": self.daily_limit_minor,
            "monthly_limit_minor": self.monthly_limit_minor,
            "channels": self.channels,
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class CardSecretView:
    masked_pan: str
    pan: str
    cvv: str
    expiry_month: int
    expiry_year: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "masked_pan": self.masked_pan,
            "pan": self.pan,
            "cvv": self.cvv,
            "expiry_month": self.expiry_month,
            "expiry_year": self.expiry_year,
        }


# --------------------------------------------------------------------- helpers
def _load_user_wallet(uow: WorkUnitOfWork, user_id: str) -> tuple[Any, Any]:
    user = uow.users.get(EntityId(user_id))
    if user is None:  # pragma: no cover - jeton valide
        raise InvalidInput("Compte introuvable.")
    user.ensure_can_transact()
    wallets = uow.wallets.list_for_user(user.id)
    if not wallets:  # pragma: no cover
        raise InvalidInput("Aucun portefeuille pour ce compte.")
    return user, wallets[0]


def _require_card(uow: WorkUnitOfWork, *, card_id: str, user_id: str) -> Card:
    try:
        card = uow.cards.get_for_update(EntityId(card_id))
    except (KeyError, ValueError) as exc:
        raise InvalidInput("Carte introuvable.") from exc
    if str(card.user_id) != user_id:
        raise InvalidInput("Carte introuvable.")
    return card


def _parse_channels(raw: list[str] | None) -> frozenset[CardChannel] | None:
    if raw is None:
        return None
    try:
        return frozenset(CardChannel(c) for c in raw)
    except ValueError as exc:
        raise InvalidInput("Canal de carte inconnu.") from exc


# ============================================================== émission
@dataclass(frozen=True, slots=True)
class IssueCardCommand(Command):
    user_id: str
    network: str = "VISA"
    daily_limit_minor: int | None = None
    monthly_limit_minor: int | None = None
    channels: list[str] | None = None


class IssueCard(UseCase[IssueCardCommand, CardView]):
    def __init__(self, *, services: AppServices, issuer: CardIssuer) -> None:
        self._services = services
        self._issuer = issuer

    def execute(self, command: IssueCardCommand) -> CardView:
        try:
            CardNetwork(command.network)
        except ValueError as exc:
            raise InvalidInput("Réseau de carte inconnu.") from exc
        channels = _parse_channels(command.channels)
        now = self._services.clock.now()
        card_id = self._services.ids.new_id()
        captured: list[CardView] = []

        def work(uow: WorkUnitOfWork) -> None:
            user, wallet = _load_user_wallet(uow, command.user_id)
            daily = Money(
                command.daily_limit_minor
                if command.daily_limit_minor is not None
                else _DEFAULT_DAILY_MINOR,
                wallet.currency,
            )
            monthly = Money(
                command.monthly_limit_minor
                if command.monthly_limit_minor is not None
                else _DEFAULT_MONTHLY_MINOR,
                wallet.currency,
            )
            issued = self._issuer.issue(
                card_id=str(card_id), holder_ref=str(user.id), network=command.network
            )
            card = Card.issue(
                card_id=card_id,
                wallet_id=EntityId(str(wallet.id)),
                user_id=user.id,
                currency=wallet.currency,
                network=CardNetwork(issued.network),
                pan_token=issued.pan_token,
                last4=issued.last4,
                expiry_month=issued.expiry_month,
                expiry_year=issued.expiry_year,
                daily_limit=daily,
                monthly_limit=monthly,
                now=now,
                channels=channels if channels is not None else frozenset(CardChannel),
            )
            uow.cards.add(card)
            captured.append(CardView.of(card))

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


# ============================================================== consultation
@dataclass(frozen=True, slots=True)
class ListCardsCommand(Command):
    user_id: str


class ListCards(UseCase[ListCardsCommand, list[CardView]]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: ListCardsCommand) -> list[CardView]:
        with self._services.uow() as uow:
            return [CardView.of(c) for c in uow.cards.list_for_user(EntityId(command.user_id))]


@dataclass(frozen=True, slots=True)
class GetCardCommand(Command):
    user_id: str
    card_id: str


class GetCard(UseCase[GetCardCommand, CardView]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: GetCardCommand) -> CardView:
        with self._services.uow() as uow:
            card = uow.cards.get(EntityId(command.card_id))
            if card is None or str(card.user_id) != command.user_id:
                raise InvalidInput("Carte introuvable.")
            return CardView.of(card)


# ============================================================== statut
@dataclass(frozen=True, slots=True)
class FreezeCardCommand(Command):
    user_id: str
    card_id: str
    reason: str = "Gel demandé par le titulaire"


@dataclass(frozen=True, slots=True)
class UnfreezeCardCommand(Command):
    user_id: str
    card_id: str


@dataclass(frozen=True, slots=True)
class CloseCardCommand(Command):
    user_id: str
    card_id: str


class _CardStatusChange:
    def __init__(self, *, services: AppServices, issuer: CardIssuer, action: str) -> None:
        self._services = services
        self._issuer = issuer
        self._action = action

    def run(self, *, user_id: str, card_id: str, reason: str | None = None) -> CardView:
        now = self._services.clock.now()
        captured: list[CardView] = []

        def work(uow: WorkUnitOfWork) -> None:
            card = _require_card(uow, card_id=card_id, user_id=user_id)
            if self._action == "freeze":
                self._issuer.freeze(card.pan_token)
                card.freeze(reason or "Gel", now)
            elif self._action == "unfreeze":
                self._issuer.unfreeze(card.pan_token)
                card.unfreeze(now)
            else:
                self._issuer.close(card.pan_token)
                card.close(now)
            uow.cards.save(card)
            captured.append(CardView.of(card))

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


class FreezeCard(UseCase[FreezeCardCommand, CardView]):
    def __init__(self, *, services: AppServices, issuer: CardIssuer) -> None:
        self._impl = _CardStatusChange(services=services, issuer=issuer, action="freeze")

    def execute(self, command: FreezeCardCommand) -> CardView:
        return self._impl.run(
            user_id=command.user_id, card_id=command.card_id, reason=command.reason
        )


class UnfreezeCard(UseCase[UnfreezeCardCommand, CardView]):
    def __init__(self, *, services: AppServices, issuer: CardIssuer) -> None:
        self._impl = _CardStatusChange(services=services, issuer=issuer, action="unfreeze")

    def execute(self, command: UnfreezeCardCommand) -> CardView:
        return self._impl.run(user_id=command.user_id, card_id=command.card_id)


class CloseCard(UseCase[CloseCardCommand, CardView]):
    def __init__(self, *, services: AppServices, issuer: CardIssuer) -> None:
        self._impl = _CardStatusChange(services=services, issuer=issuer, action="close")

    def execute(self, command: CloseCardCommand) -> CardView:
        return self._impl.run(user_id=command.user_id, card_id=command.card_id)


# ============================================================== plafonds
@dataclass(frozen=True, slots=True)
class SetCardLimitsCommand(Command):
    user_id: str
    card_id: str
    daily_limit_minor: int
    monthly_limit_minor: int


class SetCardLimits(UseCase[SetCardLimitsCommand, CardView]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: SetCardLimitsCommand) -> CardView:
        if command.daily_limit_minor <= 0 or command.monthly_limit_minor <= 0:
            raise InvalidInput("Les plafonds doivent être strictement positifs.")
        now = self._services.clock.now()
        captured: list[CardView] = []

        def work(uow: WorkUnitOfWork) -> None:
            card = _require_card(uow, card_id=command.card_id, user_id=command.user_id)
            card.set_limits(
                daily=Money(command.daily_limit_minor, card.currency),
                monthly=Money(command.monthly_limit_minor, card.currency),
                now=now,
            )
            uow.cards.save(card)
            captured.append(CardView.of(card))

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


# ============================================================== données sensibles
@dataclass(frozen=True, slots=True)
class GetCardSensitiveCommand(Command):
    user_id: str
    card_id: str


class GetCardSensitive(UseCase[GetCardSensitiveCommand, CardSecretView]):
    def __init__(self, *, services: AppServices, issuer: CardIssuer) -> None:
        self._services = services
        self._issuer = issuer

    def execute(self, command: GetCardSensitiveCommand) -> CardSecretView:
        now = self._services.clock.now()
        holder: dict[str, str] = {}

        def work(uow: WorkUnitOfWork) -> None:
            card = _require_card(uow, card_id=command.card_id, user_id=command.user_id)
            card.record_sensitive_view(now)
            uow.cards.save(card)
            holder["pan_token"] = card.pan_token
            holder["masked_pan"] = card.masked_pan

        execute_in_uow(self._services.uow, self._services.events, work)
        secret = self._issuer.reveal(holder["pan_token"])
        return CardSecretView(
            masked_pan=holder["masked_pan"],
            pan=secret.pan,
            cvv=secret.cvv,
            expiry_month=secret.expiry_month,
            expiry_year=secret.expiry_year,
        )


__all__ = [
    "CardSecretView",
    "CardView",
    "CloseCard",
    "CloseCardCommand",
    "FreezeCard",
    "FreezeCardCommand",
    "GetCard",
    "GetCardCommand",
    "GetCardSensitive",
    "GetCardSensitiveCommand",
    "IssueCard",
    "IssueCardCommand",
    "ListCards",
    "ListCardsCommand",
    "SetCardLimits",
    "SetCardLimitsCommand",
    "UnfreezeCard",
    "UnfreezeCardCommand",
]
