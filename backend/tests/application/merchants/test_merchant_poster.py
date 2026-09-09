"""Cas d'usage ``RenderMerchantPoster`` (BE-069)."""

from __future__ import annotations

from uuid import UUID

import pytest

from flash.application.merchants.operations import NotAMerchant
from flash.application.merchants.poster import (
    RenderMerchantPoster,
    RenderMerchantPosterCommand,
)
from flash.application.services import AppServices
from flash.domain.merchants.merchant import Merchant
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import XOF
from tests.support.fakes import (
    FixedClock,
    InMemoryIdempotencyStore,
    RecordingEventPublisher,
    SeqIdGenerator,
)
from tests.support.repositories import InMemoryUnitOfWork

MID = EntityId(str(UUID(int=9)))
UID = str(UUID(int=9))


class _StubRenderer:
    def __init__(self) -> None:
        self.calls: list[tuple[str, str, str]] = []

    def render(self, *, merchant_name: str, qr_payload: str, category: str) -> bytes:
        self.calls.append((merchant_name, qr_payload, category))
        return b"\x89PNG\r\n\x1a\n-stub"


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


@pytest.fixture
def services(uow: InMemoryUnitOfWork) -> AppServices:
    return AppServices(
        uow=lambda: uow,
        clock=FixedClock(),
        ids=SeqIdGenerator(),
        events=RecordingEventPublisher(),
        idempotency=InMemoryIdempotencyStore(),
    )


def _merchant(uow: InMemoryUnitOfWork) -> None:
    merchant = Merchant.enroll(
        merchant_id=MID,
        user_id=EntityId(UID),
        display_name="Chez Awa",
        category="RESTAURANT",
        currency=XOF,
        fee_bps=100,
        now=FixedClock().now(),
    )
    merchant.pull_events()
    uow.merchants.add(merchant)


def test_renders_poster_with_merchant_data(
    services: AppServices, uow: InMemoryUnitOfWork
) -> None:
    _merchant(uow)
    renderer = _StubRenderer()
    poster = RenderMerchantPoster(services=services, renderer=renderer).execute(
        RenderMerchantPosterCommand(merchant_user_id=UID)
    )
    assert poster.media_type == "image/png"
    assert poster.filename == "flash-chez-awa.png"
    assert poster.content.startswith(b"\x89PNG")
    assert renderer.calls == [("Chez Awa", f"flash://pay?m={MID}", "RESTAURANT")]


def test_non_merchant_rejected(services: AppServices) -> None:
    with pytest.raises(NotAMerchant):
        RenderMerchantPoster(services=services, renderer=_StubRenderer()).execute(
            RenderMerchantPosterCommand(merchant_user_id=UID)
        )
