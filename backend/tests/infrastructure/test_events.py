"""Tests des publishers d'événements best-effort (BE-020)."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import UTC, datetime

from flash.domain.identity.events import UserRegistered
from flash.domain.shared.events import DomainEvent
from flash.infrastructure.events import (
    CompositeEventPublisher,
    LoggingEventPublisher,
    NotifyingEventPublisher,
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


class _RecordingInner:
    def __init__(self) -> None:
        self.published: list[list[DomainEvent]] = []

    def publish(self, events: list[DomainEvent]) -> None:
        self.published.append(events)


def test_notifying_publisher_calls_inner_then_sink() -> None:
    inner = _RecordingInner()
    handled: list[list[DomainEvent]] = []

    class _Sink:
        def handle(self, events: Iterable[DomainEvent]) -> None:
            handled.append(list(events))

    NotifyingEventPublisher(inner, _Sink()).publish([_EVENT])
    assert inner.published == [[_EVENT]]
    assert handled == [[_EVENT]]


def test_notifying_publisher_swallows_sink_errors() -> None:
    inner = _RecordingInner()

    class _BoomSink:
        def handle(self, events: Iterable[DomainEvent]) -> None:
            raise RuntimeError("sink cassé")

    NotifyingEventPublisher(inner, _BoomSink()).publish([_EVENT])  # ne lève pas
    assert inner.published == [[_EVENT]]
