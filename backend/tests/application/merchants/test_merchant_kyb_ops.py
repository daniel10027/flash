"""Cas d'usage KYB marchand (BE-069) : soumission + revue back-office."""

from __future__ import annotations

from uuid import UUID

import pytest

from flash.application.merchants.kyb import (
    ReviewMerchantKyb,
    ReviewMerchantKybCommand,
    SubmitMerchantKyb,
    SubmitMerchantKybCommand,
)
from flash.application.merchants.operations import NotAMerchant
from flash.application.services import AppServices
from flash.domain.merchants.merchant import Merchant
from flash.domain.shared.errors import InvalidInput
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


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


@pytest.fixture
def events() -> RecordingEventPublisher:
    return RecordingEventPublisher()


@pytest.fixture
def services(uow: InMemoryUnitOfWork, events: RecordingEventPublisher) -> AppServices:
    return AppServices(
        uow=lambda: uow,
        clock=FixedClock(),
        ids=SeqIdGenerator(),
        events=events,
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


class TestSubmitKyb:
    def test_submit_marks_pending(
        self, services: AppServices, uow: InMemoryUnitOfWork, events: RecordingEventPublisher
    ) -> None:
        _merchant(uow)
        view = SubmitMerchantKyb(services=services).execute(
            SubmitMerchantKybCommand(merchant_user_id=UID)
        )
        assert view.kyb_status == "PENDING"
        assert "MerchantKybSubmitted" in events.names()

    def test_non_merchant_rejected(self, services: AppServices) -> None:
        with pytest.raises(NotAMerchant):
            SubmitMerchantKyb(services=services).execute(
                SubmitMerchantKybCommand(merchant_user_id=UID)
            )


class TestReviewKyb:
    def test_approve(
        self, services: AppServices, uow: InMemoryUnitOfWork, events: RecordingEventPublisher
    ) -> None:
        _merchant(uow)
        view = ReviewMerchantKyb(services=services).execute(
            ReviewMerchantKybCommand(merchant_id=str(MID), reviewer="key:admin", approve=True)
        )
        assert view.kyb_status == "APPROVED"
        assert view.kyb_reviewed_at is not None
        assert "MerchantKybApproved" in events.names()

    def test_reject_with_reason(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _merchant(uow)
        view = ReviewMerchantKyb(services=services).execute(
            ReviewMerchantKybCommand(
                merchant_id=str(MID),
                reviewer="key:compliance",
                approve=False,
                reason="RCCM manquant",
            )
        )
        assert view.kyb_status == "REJECTED"
        assert view.kyb_reason == "RCCM manquant"
        assert view.to_dict()["kyb_reason"] == "RCCM manquant"

    def test_reject_without_reason_is_invalid(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _merchant(uow)
        with pytest.raises(InvalidInput, match="motif"):
            ReviewMerchantKyb(services=services).execute(
                ReviewMerchantKybCommand(
                    merchant_id=str(MID), reviewer="r", approve=False, reason=""
                )
            )

    def test_unknown_merchant_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput, match="introuvable"):
            ReviewMerchantKyb(services=services).execute(
                ReviewMerchantKybCommand(
                    merchant_id=str(UUID(int=404)), reviewer="r", approve=True
                )
            )

    def test_malformed_merchant_id_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput, match="introuvable"):
            ReviewMerchantKyb(services=services).execute(
                ReviewMerchantKybCommand(merchant_id="not-a-uuid", reviewer="r", approve=True)
            )
