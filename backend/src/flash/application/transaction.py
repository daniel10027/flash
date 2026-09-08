"""Helper d'exécution transactionnelle.

Ouvre une Unit of Work, exécute le travail, commit, puis publie les événements de
domaine collectés. En cas d'exception, l'``__exit__`` de la UoW effectue le rollback et
aucun événement n'est publié.
"""

from __future__ import annotations

from collections.abc import Callable

from flash.domain.shared.ports import EventPublisher, UnitOfWork


def execute_in_uow[U: UnitOfWork, R](
    uow_factory: Callable[[], U],
    events: EventPublisher,
    work: Callable[[U], R],
) -> R:
    with uow_factory() as uow:
        result = work(uow)
        uow.commit()
        collected = uow.collect_new_events()
    if collected:
        events.publish(collected)
    return result


__all__ = ["execute_in_uow"]
