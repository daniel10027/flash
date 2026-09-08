"""Tests des publishers d'événements best-effort (BE-020)."""

from __future__ import annotations

from datetime import UTC, datetime

from flash.domain.identity.events import UserRegistered
from flash.infrastructure.events import (
    CompositeEventPublisher,
    LoggingEventPublisher,
    NullEventPublisher,
)

_EVENT = UserRegistered(
    occurred_at=datetime(2026, 1, 1, tzinfo=UTC),
    aggregate_id="u-1",
    country="CI",
    primary_msisdn="+2250700000001",
)


def test_logging_publisher_does_not_raise_on_reserved_kwarg() -> None:
    # Régression : structlog réserve le mot-clé "event"; le publisher doit utiliser
    # "event_name" pour ne pas planter.
    LoggingEventPublisher().publish([_EVENT, _EVENT])


def test_null_publisher_is_noop() -> None:
    NullEventPublisher().publish([_EVENT])  # ne lève pas, ne fait rien


def test_composite_isolates_handler_errors() -> None:
    seen: list[str] = []

    def ok(event: object) -> None:
        seen.append("ok")

    def boom(event: object) -> None:
        raise RuntimeError("handler cassé")

    CompositeEventPublisher([boom, ok]).publish([_EVENT])
    assert seen == ["ok"]  # l'erreur de `boom` n'empêche pas `ok`
