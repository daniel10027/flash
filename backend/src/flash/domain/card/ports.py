"""Ports du sous-domaine carte."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from flash.domain.card.authorization import CardAuthorization
from flash.domain.card.card import Card
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import Money


@runtime_checkable
class CardRepository(Protocol):
    def get(self, card_id: EntityId) -> Card | None: ...

    def get_for_update(self, card_id: EntityId) -> Card:
        """Carte avec verrou pessimiste. Lève ``KeyError`` si absente."""
        ...

    def get_by_pan_token(self, pan_token: str) -> Card | None: ...

    def list_for_user(self, user_id: EntityId) -> list[Card]: ...

    def add(self, card: Card) -> None: ...

    def save(self, card: Card) -> None: ...


@runtime_checkable
class CardAuthorizationRepository(Protocol):
    def get(self, auth_id: EntityId) -> CardAuthorization | None: ...

    def get_by_authorization_id(self, authorization_id: str) -> CardAuthorization | None: ...

    def get_for_update_by_authorization_id(self, authorization_id: str) -> CardAuthorization:
        """Autorisation (verrou pessimiste) par son id externe. Lève ``KeyError``."""
        ...

    def total_spent_since(self, card_id: EntityId, since: datetime) -> Money:
        """Somme des autorisations ``AUTHORIZED`` + ``CAPTURED`` depuis ``since``."""
        ...

    def list_for_card(self, card_id: EntityId) -> list[CardAuthorization]: ...

    def list_resolved(
        self, *, limit: int = 500, after: EntityId | None = None
    ) -> list[CardAuthorization]:
        """Autorisations ``CAPTURED`` / ``REFUNDED`` (pour le rapprochement), paginé."""
        ...

    def add(self, authorization: CardAuthorization) -> None: ...

    def save(self, authorization: CardAuthorization) -> None: ...


__all__ = ["CardAuthorizationRepository", "CardRepository"]
