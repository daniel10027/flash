"""Tests du job d'expiration (BE-044)."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import pytest

from flash.application.jobs.expire import ExpireStaleOperations
from flash.application.services import AppServices
from flash.domain.cash.order import CashOrder, CashOrderStatus
from flash.domain.merchants.charge import MerchantCharge, MerchantChargeStatus
from flash.domain.payments.request import PaymentRequest, PaymentRequestStatus
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import XOF, Money
from flash.domain.wallet.wallet import Wallet
from tests.support.fakes import (
    FixedClock,
    InMemoryIdempotencyStore,
    RecordingEventPublisher,
    SeqIdGenerator,
)
from tests.support.repositories import InMemoryUnitOfWork

CLIENT = str(UUID(int=1))
MERCHANT = str(UUID(int=2))


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


def _client_wallet(uow: InMemoryUnitOfWork, *, reserved: int = 0) -> Wallet:
    wallet = Wallet.open(
        wallet_id=EntityId(str(UUID(int=100))),
        user_id=EntityId(CLIENT),
        currency=XOF,
        now=FixedClock().now(),
    )
    wallet.credit(Money(50_000, XOF), FixedClock().now())
    if reserved:
        wallet.reserve(Money(reserved, XOF), FixedClock().now())
    wallet.pull_events()
    uow.wallets.add(wallet)
    return wallet


def _expired_withdrawal(uow: InMemoryUnitOfWork, clock: FixedClock) -> CashOrder:
    order = CashOrder.initiate_withdrawal(
        order_id=EntityId(str(UUID(int=10))),
        client_id=EntityId(CLIENT),
        amount=Money(30_000, XOF),
        fee=Money(0, XOF),
        code_hash="abc",
        expires_at=clock.now() - timedelta(minutes=1),
        now=clock.now() - timedelta(minutes=20),
    )
    order.pull_events()
    uow.cash_orders.add(order)
    return order


def _expired_request(uow: InMemoryUnitOfWork, clock: FixedClock) -> PaymentRequest:
    req = PaymentRequest.open(
        request_id=EntityId(str(UUID(int=11))),
        requester_id=EntityId(str(UUID(int=3))),
        payer_id=EntityId(CLIENT),
        amount=Money(5_000, XOF),
        now=clock.now() - timedelta(days=8),
        expires_at=clock.now() - timedelta(days=1),
    )
    req.pull_events()
    uow.payment_requests.add(req)
    return req


def _expired_charge(uow: InMemoryUnitOfWork, clock: FixedClock) -> MerchantCharge:
    charge = MerchantCharge.open(
        charge_id=EntityId(str(UUID(int=12))),
        merchant_id=EntityId(MERCHANT),
        amount=Money(7_000, XOF),
        reference="Table 9",
        now=clock.now() - timedelta(hours=2),
        expires_at=clock.now() - timedelta(minutes=5),
    )
    charge.pull_events()
    uow.merchant_charges.add(charge)
    return charge


def test_expires_withdrawal_and_releases_reservation(
    services: AppServices, uow: InMemoryUnitOfWork, clock: FixedClock
) -> None:
    _client_wallet(uow, reserved=30_000)
    _expired_withdrawal(uow, clock)

    report = ExpireStaleOperations(services=services).execute()
    assert report.withdrawals_expired == 1

    order = uow.cash_orders.get(EntityId(str(UUID(int=10))))
    assert order is not None and order.status is CashOrderStatus.EXPIRED
    wallet = uow.wallets.get_for_user(EntityId(CLIENT), XOF)
    assert wallet is not None
    assert wallet.reserved == Money(0, XOF)
    assert wallet.available == Money(50_000, XOF)


def test_expires_payment_requests_and_merchant_charges(
    services: AppServices, uow: InMemoryUnitOfWork, clock: FixedClock
) -> None:
    _expired_request(uow, clock)
    _expired_charge(uow, clock)

    report = ExpireStaleOperations(services=services).execute()
    assert report.payment_requests_expired == 1
    assert report.merchant_charges_expired == 1
    assert report.total == 2

    req = uow.payment_requests.get(EntityId(str(UUID(int=11))))
    assert req is not None and req.status is PaymentRequestStatus.EXPIRED
    charge = uow.merchant_charges.get(EntityId(str(UUID(int=12))))
    assert charge is not None and charge.status is MerchantChargeStatus.EXPIRED


def test_is_idempotent_and_ignores_fresh_operations(
    services: AppServices, uow: InMemoryUnitOfWork, clock: FixedClock
) -> None:
    _client_wallet(uow, reserved=30_000)
    _expired_withdrawal(uow, clock)
    # une demande encore valide
    PaymentRequest.open(
        request_id=EntityId(str(UUID(int=20))),
        requester_id=EntityId(str(UUID(int=3))),
        payer_id=EntityId(CLIENT),
        amount=Money(1_000, XOF),
        now=clock.now(),
        expires_at=clock.now() + timedelta(days=7),
    )

    first = ExpireStaleOperations(services=services).execute()
    assert first.total == 1
    second = ExpireStaleOperations(services=services).execute()
    assert second.total == 0  # plus rien à expirer
