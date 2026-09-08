"""Ports transverses du domaine.

Interfaces uniquement — les implémentations vivent dans ``infrastructure``. Elles sont
définies avec ``typing.Protocol`` : le domaine n'impose aucune héritage aux adapters.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from flash.domain.shared.events import DomainEvent
from flash.domain.shared.identifiers import EntityId


@runtime_checkable
class Clock(Protocol):
    """Fournit l'heure courante. Injectée pour rendre le temps testable."""

    def now(self) -> datetime:
        """Instant présent, timezone-aware (UTC)."""
        ...


@runtime_checkable
class IdGenerator(Protocol):
    """Génère des identifiants d'entité (UUIDv7 en production, séquentiel en test)."""

    def new_id(self) -> EntityId: ...


@runtime_checkable
class IdempotencyStore(Protocol):
    """Mémorise le résultat d'une opération pour une clé donnée.

    Contrat :
    - ``remember`` doit être atomique : renvoie ``True`` si la clé est nouvelle (l'appelant
      poursuit l'opération), ``False`` si elle existait déjà.
    - ``get_result`` renvoie le corps de réponse mémorisé (dict JSON-sérialisable) ou
      ``None`` si l'opération précédente n'a pas encore abouti.
    - ``save_result`` associe le résultat final à la clé.
    """

    def remember(self, key: str, *, ttl_seconds: int) -> bool: ...

    def get_result(self, key: str) -> dict[str, Any] | None: ...

    def save_result(self, key: str, result: dict[str, Any], *, ttl_seconds: int) -> None: ...


@runtime_checkable
class EventPublisher(Protocol):
    """Publie les événements de domaine collectés après un cas d'usage."""

    def publish(self, events: list[DomainEvent]) -> None: ...


@runtime_checkable
class UnitOfWork(Protocol):
    """Frontière transactionnelle. Un cas d'usage s'exécute dans un ``with uow:``.

    - À la sortie normale du bloc, ``commit`` est appelé.
    - En cas d'exception, ``rollback``.
    - Les repos concrets sont exposés en attributs par les implémentations
      (``uow.users``, ``uow.wallets``, ``uow.ledger``…). Ils ne sont pas listés ici pour
      garder ce port générique ; chaque sous-domaine définit son propre port de repo.
    """

    def __enter__(self) -> UnitOfWork: ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def collect_new_events(self) -> list[DomainEvent]:
        """Récupère les événements des agrégats manipulés pendant la transaction."""
        ...


__all__ = ["Clock", "EventPublisher", "IdGenerator", "IdempotencyStore", "UnitOfWork"]
