"""Ports du sous-système de notifications."""

from __future__ import annotations

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

    def count_unread(self, user_id: str) -> int: ...

    def mark_read(self, user_id: str, notification_id: str) -> bool: ...

    def mark_all_read(self, user_id: str) -> int: ...


__all__ = ["NotificationChannel", "NotificationRepository", "Notifier"]
