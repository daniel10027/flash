"""Publication best-effort des événements de domaine (fan-out synchrone).

La livraison **fiable** passe par la table ``outbox`` (écrite dans la transaction par la
Unit of Work) et un relais dédié. Ce module ne gère que les effets immédiats non
critiques : journalisation, métriques, poussée SSE. Toute erreur ici est avalée et
journalisée — elle ne doit jamais faire échouer une opération déjà validée.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Protocol

import structlog

from flash.domain.shared.events import DomainEvent

_log = structlog.get_logger("flash.events")

EventHandler = Callable[[DomainEvent], None]


class LoggingEventPublisher:
    """Publisher minimal : journalise chaque événement."""

    def publish(self, events: list[DomainEvent]) -> None:
        for event in events:
            _log.info("domain_event", event_name=event.name, aggregate_id=event.aggregate_id)


class CompositeEventPublisher:
    """Diffuse à plusieurs handlers, en isolant les erreurs de chacun."""

    def __init__(self, handlers: Iterable[EventHandler]) -> None:
        self._handlers = list(handlers)

    def publish(self, events: list[DomainEvent]) -> None:
        for event in events:
            for handler in self._handlers:
                try:
                    handler(event)
                except Exception:
                    _log.exception(
                        "event_handler_failed",
                        event_name=event.name,
                        handler=getattr(handler, "__name__", repr(handler)),
                    )


class NullEventPublisher:
    """Ne fait rien (utile quand seule l'outbox compte)."""

    def publish(self, events: list[DomainEvent]) -> None:
        return None


class _Publisher(Protocol):
    def publish(self, events: list[DomainEvent]) -> None: ...


class _EventSink(Protocol):
    def handle(self, events: Iterable[DomainEvent]) -> None: ...


class NotifyingEventPublisher:
    """Publie via ``inner`` puis alimente un consommateur (ex. dispatcher de
    notifications). Best-effort : une erreur du consommateur est journalisée, pas levée."""

    def __init__(self, inner: _Publisher, sink: _EventSink) -> None:
        self._inner = inner
        self._sink = sink

    def publish(self, events: list[DomainEvent]) -> None:
        self._inner.publish(events)
        try:
            self._sink.handle(events)
        except Exception:
            _log.exception("event_sink_failed", count=len(events))


__all__ = [
    "CompositeEventPublisher",
    "EventHandler",
    "LoggingEventPublisher",
    "NotifyingEventPublisher",
    "NullEventPublisher",
]
