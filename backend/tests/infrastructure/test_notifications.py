"""Tests des canaux de notification et du FanOutNotifier (BE-040)."""

from __future__ import annotations

import smtplib
from datetime import UTC, datetime

import pytest

from flash.application.notifications.model import Notification, NotificationKind
from flash.infrastructure.notifications import (
    FanOutNotifier,
    FcmPushChannel,
    InAppChannel,
    LoggingNotificationChannel,
    SmtpEmailChannel,
)
from tests.support.notifications import (
    BoomChannel,
    InMemoryNotificationRepository,
    RecordingChannel,
)

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _note(**over: object) -> Notification:
    base: dict[str, object] = {
        "id": "n-1",
        "user_id": "u-1",
        "kind": NotificationKind.MONEY_IN,
        "title": "Argent reçu",
        "body": "Vous avez reçu 10 000 XOF.",
        "created_at": T0,
    }
    base.update(over)
    return Notification(**base)  # type: ignore[arg-type]


def test_fanout_delivers_to_all_channels_and_isolates_errors() -> None:
    ok1, ok2 = RecordingChannel(), RecordingChannel()
    FanOutNotifier([ok1, BoomChannel(), ok2]).deliver(_note())
    assert len(ok1.sent) == 1 and len(ok2.sent) == 1  # BoomChannel n'a pas cassé la chaîne


def test_inapp_channel_persists() -> None:
    repo = InMemoryNotificationRepository()
    InAppChannel(repo).send(_note())
    assert repo.get("n-1") is not None


def test_logging_channel_is_noop() -> None:
    LoggingNotificationChannel().send(_note())  # ne lève pas


def test_push_channel_skips_without_token_or_config() -> None:
    FcmPushChannel(credentials_json="").send(_note())  # désactivé -> no-op
    FcmPushChannel(credentials_json="{...}").send(_note())  # activé mais pas de jeton -> no-op
    FcmPushChannel(credentials_json="{...}").send(_note(data={"device_token": "tok"}))  # log


def test_email_channel_skips_without_address() -> None:
    sent: list[object] = []

    class _FakeSMTP:
        def __init__(self, *a: object, **k: object) -> None: ...
        def __enter__(self) -> _FakeSMTP:
            return self

        def __exit__(self, *a: object) -> None: ...
        def send_message(self, message: object) -> None:
            sent.append(message)

    channel = SmtpEmailChannel(host="localhost", port=1025, sender="Flash <no@flash>")
    channel.send(_note())  # pas d'adresse -> rien
    assert sent == []


def test_email_channel_sends_when_address_present(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: list[object] = []

    class _FakeSMTP:
        def __init__(self, *a: object, **k: object) -> None: ...
        def __enter__(self) -> _FakeSMTP:
            return self

        def __exit__(self, *a: object) -> None: ...
        def send_message(self, message: object) -> None:
            captured.append(message)

    monkeypatch.setattr(smtplib, "SMTP", _FakeSMTP)
    channel = SmtpEmailChannel(host="localhost", port=1025, sender="Flash <no@flash>")
    channel.send(_note(data={"email": "u@example.com"}))
    assert len(captured) == 1
