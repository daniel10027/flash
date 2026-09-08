"""Test du conteneur de dépendances applicatives (BE-015)."""

from __future__ import annotations

from flash.application.services import AppServices
from tests.support.fakes import (
    FixedClock,
    InMemoryIdempotencyStore,
    RecordingEventPublisher,
    SeqIdGenerator,
)
from tests.support.repositories import InMemoryUnitOfWork


def test_app_services_bundles_transverse_ports() -> None:
    uow = InMemoryUnitOfWork()
    services = AppServices(
        uow=lambda: uow,
        clock=FixedClock(),
        ids=SeqIdGenerator(),
        events=RecordingEventPublisher(),
        idempotency=InMemoryIdempotencyStore(),
    )
    assert services.uow() is uow
    assert services.clock.now().year == 2026
    assert str(services.ids.new_id())  # génère un identifiant valide
