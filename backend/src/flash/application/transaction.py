"""Helper d'exécution transactionnelle.

Ouvre une Unit of Work, exécute le travail, commit, puis publie les événements de
domaine collectés. En cas d'exception, l'``__exit__`` de la UoW effectue le rollback et
aucun événement n'est publié.
"""

from __future__ import annotations

from collections.abc import Callable

from flash.application.unit_of_work import WorkUnitOfWork
from flash.domain.shared.ports import EventPublisher


def execute_in_uow[R](
    uow_factory: Callable[[], WorkUnitOfWork],
    events: EventPublisher,
    work: Callable[[WorkUnitOfWork], R],
) -> R:
    with uow_factory() as uow:
        result = work(uow)
        uow.commit()
        collected = uow.collect_new_events()
    if collected:
        events.publish(collected)
    return result


__all__ = ["execute_in_uow"]
