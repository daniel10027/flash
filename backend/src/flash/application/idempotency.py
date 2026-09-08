"""Idempotence des opérations applicatives.

Toute opération qui déplace de l'argent accepte une ``Idempotency-Key``. Rejouer la même
clé renvoie le résultat mémorisé au lieu de refaire l'opération.

``IdempotencyGuard.run`` encadre l'exécution :
- clé déjà terminée  -> on reconstruit le résultat depuis le payload stocké (``replayed``)
- clé nouvelle       -> on exécute, on mémorise le payload, on renvoie le résultat
- clé en cours (course) sans résultat encore stocké -> ``DuplicateOperation``
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from flash.domain.shared.errors import DuplicateOperation
from flash.domain.shared.identifiers import EntityId, IdempotencyKey
from flash.domain.shared.ports import IdempotencyStore

DEFAULT_TTL_SECONDS = 24 * 3600


@dataclass(frozen=True, slots=True)
class IdempotencyOutcome[R]:
    result: R
    replayed: bool


class IdempotencyGuard:
    def __init__(self, store: IdempotencyStore, *, ttl_seconds: int = DEFAULT_TTL_SECONDS) -> None:
        self._store = store
        self._ttl = ttl_seconds

    def run[R](
        self,
        *,
        key: IdempotencyKey,
        user_id: EntityId,
        route: str,
        produce: Callable[[], tuple[R, dict[str, Any]]],
        rebuild: Callable[[dict[str, Any]], R],
    ) -> IdempotencyOutcome[R]:
        scoped = key.scoped(user_id=str(user_id), route=route)

        cached = self._store.get_result(scoped)
        if cached is not None:
            return IdempotencyOutcome(rebuild(cached), replayed=True)

        if not self._store.remember(scoped, ttl_seconds=self._ttl):
            cached = self._store.get_result(scoped)
            if cached is not None:
                return IdempotencyOutcome(rebuild(cached), replayed=True)
            raise DuplicateOperation()

        result, payload = produce()
        self._store.save_result(scoped, payload, ttl_seconds=self._ttl)
        return IdempotencyOutcome(result, replayed=False)


__all__ = ["DEFAULT_TTL_SECONDS", "IdempotencyGuard", "IdempotencyOutcome"]
