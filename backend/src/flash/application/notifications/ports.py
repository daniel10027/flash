"""Ports du sous-système de notifications."""

from __future__ import annotations

from collections.abc import Iterator
from typing import Protocol, runtime_checkable

from flash.application.notifications.model import Notification


@runtime_checkable
class NotificationChannel(Protocol):
    """Un canal de livraison (in-app, e-mail, push)."""

    def send(self, notification: Notification) -> None: ...


@runtime_checkable
class Notifier(Protocol):
    """Point d'entrée : diffuse une notification sur tous les canaux configurés.

    Best-effort : toute erreur d'un canal est isolée et ne remonte pas.
    """

    def deliver(self, notification: Notification) -> None: ...


@runtime_checkable
class NotificationRepository(Protocol):
    """Journal in-app des notifications (sa propre transaction, hors UoW métier)."""

    def add(self, notification: Notification) -> None: ...

    def get(self, notification_id: str) -> Notification | None: ...

    def list_for_user(
        self, user_id: str, *, unread_only: bool = False, limit: int = 20, before: str | None = None
    ) -> list[Notification]: ...

    def list_since(self, user_id: str, after_id: str, *, limit: int = 100) -> list[Notification]:
        """Notifications de ``user_id`` d'id **strictement supérieur** à ``after_id``,
        les plus anciennes d'abord (rattrapage après reconnexion SSE)."""
        ...

    def count_unread(self, user_id: str) -> int: ...

    def mark_read(self, user_id: str, notification_id: str) -> bool: ...

    def mark_all_read(self, user_id: str) -> int: ...


@runtime_checkable
class NotificationBus(Protocol):
    """Bus temps réel (pub/sub) entre le point de livraison et les flux SSE.

    Permet à un worker de pousser une notification vers un flux SSE tenu par un
    **autre** worker (Redis pub/sub en production).
    """

    def publish(self, notification: Notification) -> None: ...

    def subscribe(self, user_id: str) -> Iterator[Notification | None]:
        """Itère les notifications live de ``user_id``. Émet ``None`` périodiquement
        (occasion d'envoyer un keep-alive) et lorsqu'il n'y a rien de nouveau."""
        ...


__all__ = [
    "NotificationBus",
    "NotificationChannel",
    "NotificationRepository",
    "Notifier",
]
