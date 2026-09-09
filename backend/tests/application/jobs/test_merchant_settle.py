"""Tests du job de règlement marchand (BE-070) : ``SettleDueMerchants``."""

from __future__ import annotations

from uuid import UUID

import pytest

from flash.application.jobs.merchant_settle import SettleDueMerchants
from flash.application.merchants.bank import BankAck
from flash.application.merchants.settlement import (
    ConfigureMerchantSettlement,
    ConfigureMerchantSettlementCommand,
)
from flash.application.services import AppServices
from flash.domain.merchants.merchant import Merchant
from flash.domain.merchants.payment import MerchantPayment
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import XOF, Money
from tests.support.fakes import (
    FixedClock,
    InMemoryIdempotencyStore,
    RecordingEventPublisher,
    SeqIdGenerator,
)
from tests.support.repositories import InMemoryUnitOfWork

IBAN = "CI93CI0080111301134291200589"


class _Bank:
    def transfer(self, **_: object) -> BankAck:
        return BankAck(accepted=True, bank_reference="bank_ref")


class _RejectingBank:
    def transfer(self, **_: object) -> BankAck:
        return BankAck(accepted=False, bank_reference="", reason="Compte clos")


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def services(uow: InMemoryUnitOfWork, clock: FixedClock) -> AppServices:
    return AppServices(
        uow=lambda: uow,
        clock=clock,
        ids=SeqIdGenerator(),
        events=RecordingEventPublisher(),
        idempotency=InMemoryIdempotencyStore(),
    )


def _merchant(uow: InMemoryUnitOfWork, *, n: int) -> EntityId:
    mid = EntityId(str(UUID(int=n)))
    merchant = Merchant.enroll(
        merchant_id=mid,
        user_id=EntityId(str(UUID(int=n))),
        display_name=f"Marchand {n}",
        category="GENERAL",
        currency=XOF,
        fee_bps=100,
        now=FixedClock().now(),
    )
    merchant.pull_events()
    uow.merchants.add(merchant)
    return mid


def _payment(uow: InMemoryUnitOfWork, mid: EntityId, *, n: int, amount: int) -> None:
    payment = MerchantPayment.record(
        payment_id=EntityId(str(UUID(int=1000 + n))),
        payer_id=EntityId(str(UUID(int=5000))),
        merchant_id=mid,
        amount=Money(amount, XOF),
        fee=Money(amount // 100, XOF),
        reference=f"ref-{n}",
        ledger_transaction_id=EntityId(str(UUID(int=2000 + n))),
        now=FixedClock().now(),
    )
    payment.pull_events()
    uow.merchant_payments.add(payment)


def _configure_daily(services: AppServices, mid_user: int) -> None:
    ConfigureMerchantSettlement(services=services).execute(
        ConfigureMerchantSettlementCommand(
            merchant_user_id=str(UUID(int=mid_user)),
            holder="Titulaire",
            iban=IBAN,
            bank_name="Ecobank",
            frequency="DAILY",
        )
    )


class TestSettleDueMerchants:
    def test_settles_due_merchant_with_encours(
        self, services: AppServices, uow: InMemoryUnitOfWork, clock: FixedClock
    ) -> None:
        mid = _merchant(uow, n=7)
        _payment(uow, mid, n=1, amount=10_000)
        _configure_daily(services, 7)
        clock.advance(days=1)

        report = SettleDueMerchants(services=services, bank=_Bank()).execute()
        assert report.checked == 1
        assert report.settled == 1
        assert report.settled_minor == 10_000 - 100
        assert report.skipped == 0 and report.failed == 0
        assert report.to_dict()["settled"] == 1

    def test_skips_due_merchant_without_encours(
        self, services: AppServices, uow: InMemoryUnitOfWork, clock: FixedClock
    ) -> None:
        _merchant(uow, n=7)
        _configure_daily(services, 7)
        clock.advance(days=1)

        report = SettleDueMerchants(services=services, bank=_Bank()).execute()
        assert report.checked == 1 and report.skipped == 1 and report.settled == 0

    def test_ignores_merchant_not_yet_due(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        mid = _merchant(uow, n=7)
        _payment(uow, mid, n=1, amount=10_000)
        _configure_daily(services, 7)

        report = SettleDueMerchants(services=services, bank=_Bank()).execute()
        assert report.checked == 0 and report.settled == 0

    def test_counts_failed_when_bank_rejects(
        self, services: AppServices, uow: InMemoryUnitOfWork, clock: FixedClock
    ) -> None:
        mid = _merchant(uow, n=7)
        _payment(uow, mid, n=1, amount=10_000)
        _configure_daily(services, 7)
        clock.advance(days=1)

        report = SettleDueMerchants(services=services, bank=_RejectingBank()).execute()
        assert report.checked == 1
        assert report.failed == 1
        assert report.settled == 0 and report.skipped == 0
        assert report.settled_minor == 0

    def test_rerun_is_idempotent(
        self, services: AppServices, uow: InMemoryUnitOfWork, clock: FixedClock
    ) -> None:
        mid = _merchant(uow, n=7)
        _payment(uow, mid, n=1, amount=10_000)
        _configure_daily(services, 7)
        clock.advance(days=1)

        SettleDueMerchants(services=services, bank=_Bank()).execute()
        second = SettleDueMerchants(services=services, bank=_Bank()).execute()
        assert second.checked == 0 and second.settled == 0
