"""Canaux de notification et ``FanOutNotifier``.

- ``InAppChannel`` : persiste dans le journal in-app (lu par ``GET /v1/notifications``,
  poussé en SSE par ``BE-041``).
- ``SmtpEmailChannel`` : envoie un e-mail **si** la notification porte une adresse
  (``data["email"]``) — Flash étant sans e-mail par défaut, ce canal reste inerte tant
  qu'un flux n'attache pas d'adresse.
- ``FcmPushChannel`` : push mobile **si** un jeton d'appareil est fourni
  (``data["device_token"]``) et FCM configuré ; sinon journalise seulement.
- ``LoggingNotificationChannel`` : trace (dev / secours).
"""

from __future__ import annotations

import smtplib
from collections.abc import Iterable
from email.message import EmailMessage

import structlog

from flash.application.notifications.model import Notification
from flash.application.notifications.ports import (
    NotificationBus,
    NotificationChannel,
    NotificationRepository,
)

_log = structlog.get_logger("flash.notifications")


class LoggingNotificationChannel(NotificationChannel):
    def send(self, notification: Notification) -> None:
        _log.info(
            "notification",
            user_id=notification.user_id,
            kind=notification.kind.value,
            title=notification.title,
        )


class InAppChannel(NotificationChannel):
    def __init__(self, repository: NotificationRepository) -> None:
        self._repo = repository

    def send(self, notification: Notification) -> None:
        self._repo.add(notification)


class BusChannel(NotificationChannel):
    """Republie la notification sur le bus temps réel (pour les flux SSE)."""

    def __init__(self, bus: NotificationBus) -> None:
        self._bus = bus

    def send(self, notification: Notification) -> None:
        self._bus.publish(notification)


class SmtpEmailChannel(NotificationChannel):
    def __init__(self, *, host: str, port: int, sender: str, timeout: float = 5.0) -> None:
        self._host = host
        self._port = port
        self._sender = sender
        self._timeout = timeout

    def send(self, notification: Notification) -> None:
        to = notification.data.get("email")
        if not to:
            return
        message = EmailMessage()
        message["From"] = self._sender
        message["To"] = str(to)
        message["Subject"] = notification.title
        message.set_content(notification.body)
        with smtplib.SMTP(self._host, self._port, timeout=self._timeout) as client:
            client.send_message(message)


class FcmPushChannel(NotificationChannel):
    def __init__(self, *, credentials_json: str) -> None:
        self._enabled = bool(credentials_json.strip())

    def send(self, notification: Notification) -> None:
        token = notification.data.get("device_token")
        if not self._enabled or not token:
            _log.debug(
                "push_skipped",
                user_id=notification.user_id,
                enabled=self._enabled,
                has_token=bool(token),
            )
            return
        # L'envoi réel FCM (HTTP v1) sera branché avec la collecte des jetons (BE-042).
        _log.info("push_would_send", user_id=notification.user_id, title=notification.title)


class FanOutNotifier:
    """Diffuse sur tous les canaux ; toute erreur d'un canal est isolée et journalisée."""

    def __init__(self, channels: Iterable[NotificationChannel]) -> None:
        self._channels = list(channels)

    def deliver(self, notification: Notification) -> None:
        for channel in self._channels:
            try:
                channel.send(notification)
            except Exception:
                _log.exception(
                    "notification_channel_failed",
                    channel=type(channel).__name__,
                    user_id=notification.user_id,
                )


__all__ = [
    "BusChannel",
    "FanOutNotifier",
    "FcmPushChannel",
    "InAppChannel",
    "LoggingNotificationChannel",
    "SmtpEmailChannel",
]
