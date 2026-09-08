"""Tests de RefundMerchantPayment (BE-037)."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import pytest

from flash.application.merchants.operations import (
    EnrollMerchant,
    EnrollMerchantCommand,
    NotAMerchant,
    PayMerchant,
    PayMerchantCommand,
)
from flash.application.merchants.refund import (
    RefundMerchantPayment,
    RefundMerchantPaymentCommand,
)
from flash.application.services import AppServices
from flash.domain.identity.pin import Pin
from flash.domain.identity.user import User
from flash.domain.ledger.transaction import TransactionKind
from flash.domain.limits.limits import KycPolicy, LimitPolicy
from flash.domain.shared.errors import DuplicateOperation, InvalidInput, ReversalWindowClosed
from flash.domain.shared.identifiers import CountryCode, EntityId, Msisdn
from flash.domain.shared.money import XOF, Money
from flash.domain.wallet.wallet import Wallet
from flash.infrastructure.limits import NullLimitCounter, build_limit_repository
from tests.support.fakes import (
    FakePinHasher,
    FixedClock,
    InMemoryIdempotencyStore,
    RecordingEventPublisher,
    SeqIdGenerator,
)
from tests.support.repositories import InMemoryUnitOfWork

CI = CountryCode("CI")
MERCHANT_MSISDN = "+2250700000009"
PAYER_MSISDN = "+2250700000001"
MERCHANT_ID = str(UUID(int=9))
PAYER_ID = str(UUID(int=1))
WINDOW = timedelta(hours=1)


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


def _user(uow: InMemoryUnitOfWork, *, n: int, msisdn: str, balance: int = 0) -> User:
    user = User.register(
        user_id=EntityId(str(UUID(int=n))),
        country=CI,
        msisdn=Msisdn(msisdn),
        pin_hash=FakePinHasher().hash(Pin("1397")),
        now=FixedClock().now(),
    )
    user.activate(FixedClock().now())
    user.pull_events()
    uow.users.add(user)
    wallet = Wallet.open(
        wallet_id=EntityId(str(UUID(int=500 + n))),
        user_id=user.id,
        currency=XOF,
        now=FixedClock().now(),
    )
    if balance:
        wallet.credit(Money(balance, XOF), FixedClock().now())
    wallet.pull_events()
    uow.wallets.add(wallet)
    return user


def _setup_paid(services: AppServices, uow: InMemoryUnitOfWork, *, amount: int = 25_000) -> str:
    _user(uow, n=9, msisdn=MERCHANT_MSISDN)
    merchant = EnrollMerchant(services=services).execute(
        EnrollMerchantCommand(user_id=MERCHANT_ID, display_name="Chez Awa", fee_bps=100)
    )
    _user(uow, n=1, msisdn=PAYER_MSISDN, balance=100_000)
    receipt = PayMerchant(
        services=services,
        limits=LimitPolicy(build_limit_repository(), NullLimitCounter()),
        kyc=KycPolicy(),
    ).execute(
        PayMerchantCommand(
            payer_user_id=PAYER_ID,
            merchant_id=merchant.merchant_id,
            idempotency_key="mpay-key-0001",
            amount_minor=amount,
        )
    )
    return receipt.payment_id


def _refund_uc(services: AppServices) -> RefundMerchantPayment:
    return RefundMerchantPayment(services=services, window=WINDOW)


class TestRefundMerchantPayment:
    def test_refund_credits_payer_and_reverses_ledger(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        payment_id = _setup_paid(services, uow, amount=25_000)
        payer_wallet = uow.wallets.get_for_user(EntityId(PAYER_ID), XOF)
        assert payer_wallet is not None and payer_wallet.available == Money(75_000, XOF)

        receipt = _refund_uc(services).execute(
            RefundMerchantPaymentCommand(
                merchant_user_id=MERCHANT_ID,
                payment_id=payment_id,
                idempotency_key="refund-key-0001",
            )
        )
        assert receipt.status == "REFUNDED"
        assert receipt.amount_minor == 25_000

        payer_wallet = uow.wallets.get_for_user(EntityId(PAYER_ID), XOF)
        assert payer_wallet is not None and payer_wallet.available == Money(100_000, XOF)

        payment = uow.merchant_payments.get(EntityId(payment_id))
        assert payment is not None and payment.status.value == "REFUNDED"
        txns = uow.ledger.get_by_reference(f"MPY-{payment_id}")
        assert sorted(t.kind for t in txns) == sorted(
            [TransactionKind.MERCHANT_PAYMENT, TransactionKind.REVERSAL]
        )
        assert all(t.is_balanced for t in txns)

    def test_refund_same_key_replays_receipt(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        payment_id = _setup_paid(services, uow)
        uc = _refund_uc(services)
        cmd = RefundMerchantPaymentCommand(
            merchant_user_id=MERCHANT_ID, payment_id=payment_id, idempotency_key="refund-rep"
        )
        assert uc.execute(cmd) == uc.execute(cmd)

    def test_refund_twice_rejected(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        payment_id = _setup_paid(services, uow)
        _refund_uc(services).execute(
            RefundMerchantPaymentCommand(
                merchant_user_id=MERCHANT_ID, payment_id=payment_id, idempotency_key="refund-a"
            )
        )
        with pytest.raises(DuplicateOperation):
            _refund_uc(services).execute(
                RefundMerchantPaymentCommand(
                    merchant_user_id=MERCHANT_ID, payment_id=payment_id, idempotency_key="refund-b"
                )
            )

    def test_refund_by_other_merchant_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        payment_id = _setup_paid(services, uow)
        _user(uow, n=2, msisdn="+2250700000002")
        EnrollMerchant(services=services).execute(
            EnrollMerchantCommand(user_id=str(UUID(int=2)), display_name="Autre")
        )
        with pytest.raises(InvalidInput, match="introuvable"):
            _refund_uc(services).execute(
                RefundMerchantPaymentCommand(
                    merchant_user_id=str(UUID(int=2)),
                    payment_id=payment_id,
                    idempotency_key="refund-xmerch",
                )
            )

    def test_refund_by_non_merchant_rejected(self, services: AppServices) -> None:
        with pytest.raises(NotAMerchant):
            _refund_uc(services).execute(
                RefundMerchantPaymentCommand(
                    merchant_user_id=str(UUID(int=3)),
                    payment_id=str(UUID(int=1)),
                    idempotency_key="refund-nomerch",
                )
            )

    def test_window_closed_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork, clock: FixedClock
    ) -> None:
        payment_id = _setup_paid(services, uow)
        clock.advance(hours=2)
        with pytest.raises(ReversalWindowClosed):
            _refund_uc(services).execute(
                RefundMerchantPaymentCommand(
                    merchant_user_id=MERCHANT_ID,
                    payment_id=payment_id,
                    idempotency_key="refund-old",
                )
            )

    def test_unknown_payment_rejected(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        _user(uow, n=9, msisdn=MERCHANT_MSISDN)
        EnrollMerchant(services=services).execute(
            EnrollMerchantCommand(user_id=MERCHANT_ID, display_name="Chez Awa")
        )
        with pytest.raises(InvalidInput, match="introuvable"):
            _refund_uc(services).execute(
                RefundMerchantPaymentCommand(
                    merchant_user_id=MERCHANT_ID,
                    payment_id=str(UUID(int=404)),
                    idempotency_key="refund-none",
                )
            )

    def test_bad_idempotency_key_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput):
            _refund_uc(services).execute(
                RefundMerchantPaymentCommand(
                    merchant_user_id=MERCHANT_ID,
                    payment_id=str(UUID(int=1)),
                    idempotency_key="x",
                )
            )
