"""Tests des cas d'usage marchands : enrôlement, QR, paiement (BE-033)."""

from __future__ import annotations

from uuid import UUID

import pytest

from flash.application.merchants.operations import (
    CreateMerchantCharge,
    CreateMerchantChargeCommand,
    EnrollMerchant,
    EnrollMerchantCommand,
    GetMerchantQr,
    GetMerchantQrCommand,
    ListMerchantPayments,
    ListMerchantPaymentsCommand,
    NotAMerchant,
    PayMerchant,
    PayMerchantCommand,
)
from flash.application.services import AppServices
from flash.domain.identity.pin import Pin
from flash.domain.identity.user import User
from flash.domain.ledger.transaction import sum_postings
from flash.domain.limits.limits import KycPolicy, LimitPolicy
from flash.domain.shared.errors import InsufficientFunds, InvalidAccountState, InvalidInput
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


def _enroll(services: AppServices, uow: InMemoryUnitOfWork, *, fee_bps: int = 100) -> str:
    _user(uow, n=9, msisdn=MERCHANT_MSISDN)
    view = EnrollMerchant(services=services).execute(
        EnrollMerchantCommand(user_id=MERCHANT_ID, display_name="Chez Awa", fee_bps=fee_bps)
    )
    return view.merchant_id


def _pay_uc(services: AppServices) -> PayMerchant:
    return PayMerchant(
        services=services,
        limits=LimitPolicy(build_limit_repository(), NullLimitCounter()),
        kyc=KycPolicy(),
    )


class TestEnrollAndQr:
    def test_enroll_then_static_qr(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        merchant_id = _enroll(services, uow)
        qr = GetMerchantQr(services=services).execute(
            GetMerchantQrCommand(merchant_user_id=MERCHANT_ID)
        )
        assert qr.static_qr_payload == f"flash://pay?m={merchant_id}"
        assert qr.fee_bps == 100

    def test_enroll_twice_rejected(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        _enroll(services, uow)
        with pytest.raises(InvalidAccountState):
            EnrollMerchant(services=services).execute(
                EnrollMerchantCommand(user_id=MERCHANT_ID, display_name="Bis")
            )

    def test_enroll_unknown_user_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput, match="introuvable"):
            EnrollMerchant(services=services).execute(
                EnrollMerchantCommand(user_id=str(UUID(int=404)), display_name="X")
            )

    def test_enroll_blank_name_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput):
            EnrollMerchant(services=services).execute(
                EnrollMerchantCommand(user_id=MERCHANT_ID, display_name="   ")
            )

    def test_qr_for_non_merchant_rejected(self, services: AppServices) -> None:
        with pytest.raises(NotAMerchant):
            GetMerchantQr(services=services).execute(
                GetMerchantQrCommand(merchant_user_id=str(UUID(int=2)))
            )


class TestStaticQrPayment:
    def test_pay_debits_payer_and_credits_merchant_net(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        merchant_id = _enroll(services, uow)
        _user(uow, n=1, msisdn=PAYER_MSISDN, balance=100_000)

        receipt = _pay_uc(services).execute(
            PayMerchantCommand(
                payer_user_id=PAYER_ID,
                merchant_id=merchant_id,
                idempotency_key="mpay-key-0001",
                amount_minor=25_000,
            )
        )
        assert receipt.amount_minor == 25_000
        assert receipt.fee_minor == 250  # 1 %
        assert receipt.payer_balance_after_minor == 75_000

        wallet = uow.wallets.get_for_user(EntityId(PAYER_ID), XOF)
        assert wallet is not None
        assert wallet.available == Money(75_000, XOF)

        [txn] = uow.ledger.get_by_reference(f"MPY-{receipt.payment_id}")
        assert txn.is_balanced and sum_postings(txn.postings) == {"XOF": 0}
        [payment] = uow.merchant_payments.list_for_merchant(EntityId(merchant_id))
        assert payment.net_to_merchant == Money(24_750, XOF)

    def test_pay_bad_idempotency_key_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        merchant_id = _enroll(services, uow)
        _user(uow, n=1, msisdn=PAYER_MSISDN, balance=100_000)
        with pytest.raises(InvalidInput):
            _pay_uc(services).execute(
                PayMerchantCommand(
                    payer_user_id=PAYER_ID,
                    merchant_id=merchant_id,
                    idempotency_key="x",
                    amount_minor=1_000,
                )
            )

    def test_pay_malformed_merchant_id_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput):
            _pay_uc(services).execute(
                PayMerchantCommand(
                    payer_user_id=PAYER_ID,
                    merchant_id="not-a-uuid",
                    idempotency_key="mpay-key-badid",
                    amount_minor=1_000,
                )
            )

    def test_static_payment_requires_amount(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        merchant_id = _enroll(services, uow)
        _user(uow, n=1, msisdn=PAYER_MSISDN, balance=100_000)
        with pytest.raises(InvalidInput, match="Montant requis"):
            _pay_uc(services).execute(
                PayMerchantCommand(
                    payer_user_id=PAYER_ID,
                    merchant_id=merchant_id,
                    idempotency_key="mpay-key-noamt",
                )
            )

    def test_pay_unknown_merchant_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, n=1, msisdn=PAYER_MSISDN, balance=100_000)
        with pytest.raises(NotAMerchant):
            _pay_uc(services).execute(
                PayMerchantCommand(
                    payer_user_id=PAYER_ID,
                    merchant_id=str(UUID(int=123)),
                    idempotency_key="mpay-key-nomerch",
                    amount_minor=1_000,
                )
            )

    def test_pay_insufficient_funds_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        merchant_id = _enroll(services, uow)
        _user(uow, n=1, msisdn=PAYER_MSISDN, balance=1_000)
        with pytest.raises(InsufficientFunds):
            _pay_uc(services).execute(
                PayMerchantCommand(
                    payer_user_id=PAYER_ID,
                    merchant_id=merchant_id,
                    idempotency_key="mpay-key-broke",
                    amount_minor=25_000,
                )
            )

    def test_merchant_cannot_pay_self(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        merchant_id = _enroll(services, uow)
        with pytest.raises(InvalidInput, match="lui-même"):
            _pay_uc(services).execute(
                PayMerchantCommand(
                    payer_user_id=MERCHANT_ID,
                    merchant_id=merchant_id,
                    idempotency_key="mpay-key-self",
                    amount_minor=1_000,
                )
            )

    def test_pay_is_idempotent(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        merchant_id = _enroll(services, uow)
        _user(uow, n=1, msisdn=PAYER_MSISDN, balance=100_000)
        cmd = PayMerchantCommand(
            payer_user_id=PAYER_ID,
            merchant_id=merchant_id,
            idempotency_key="mpay-key-rep",
            amount_minor=25_000,
        )
        first = _pay_uc(services).execute(cmd)
        second = _pay_uc(services).execute(cmd)
        assert second == first
        wallet = uow.wallets.get_for_user(EntityId(PAYER_ID), XOF)
        assert wallet is not None
        assert wallet.available == Money(75_000, XOF)  # débité une seule fois

    def test_zero_fee_merchant(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        merchant_id = _enroll(services, uow, fee_bps=0)
        _user(uow, n=1, msisdn=PAYER_MSISDN, balance=100_000)
        receipt = _pay_uc(services).execute(
            PayMerchantCommand(
                payer_user_id=PAYER_ID,
                merchant_id=merchant_id,
                idempotency_key="mpay-key-zero",
                amount_minor=25_000,
            )
        )
        assert receipt.fee_minor == 0


class TestDynamicQrPayment:
    def test_charge_then_pay_exact_amount(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        merchant_id = _enroll(services, uow)
        _user(uow, n=1, msisdn=PAYER_MSISDN, balance=100_000)
        charge = CreateMerchantCharge(services=services).execute(
            CreateMerchantChargeCommand(
                merchant_user_id=MERCHANT_ID, amount_minor=30_000, reference="Table 7"
            )
        )
        assert charge.qr_payload == f"flash://pay?m={merchant_id}&c={charge.charge_id}"

        receipt = _pay_uc(services).execute(
            PayMerchantCommand(
                payer_user_id=PAYER_ID,
                merchant_id=merchant_id,
                idempotency_key="mpay-key-dyn1",
                charge_id=charge.charge_id,
            )
        )
        assert receipt.amount_minor == 30_000
        assert receipt.reference == "Table 7"
        stored = uow.merchant_charges.get(EntityId(charge.charge_id))
        assert stored is not None and stored.status.value == "PAID"

    def test_charge_cannot_be_paid_twice(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        merchant_id = _enroll(services, uow)
        _user(uow, n=1, msisdn=PAYER_MSISDN, balance=100_000)
        charge = CreateMerchantCharge(services=services).execute(
            CreateMerchantChargeCommand(
                merchant_user_id=MERCHANT_ID, amount_minor=30_000, reference="T"
            )
        )
        _pay_uc(services).execute(
            PayMerchantCommand(
                payer_user_id=PAYER_ID,
                merchant_id=merchant_id,
                idempotency_key="mpay-key-dyn-a",
                charge_id=charge.charge_id,
            )
        )
        with pytest.raises(InvalidAccountState, match="plus payable"):
            _pay_uc(services).execute(
                PayMerchantCommand(
                    payer_user_id=PAYER_ID,
                    merchant_id=merchant_id,
                    idempotency_key="mpay-key-dyn-b",
                    charge_id=charge.charge_id,
                )
            )

    def test_charge_wrong_merchant_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _enroll(services, uow)
        _user(uow, n=1, msisdn=PAYER_MSISDN, balance=100_000)
        _user(uow, n=2, msisdn="+2250700000002")
        other = EnrollMerchant(services=services).execute(
            EnrollMerchantCommand(user_id=str(UUID(int=2)), display_name="Autre")
        )
        charge = CreateMerchantCharge(services=services).execute(
            CreateMerchantChargeCommand(
                merchant_user_id=MERCHANT_ID, amount_minor=1_000, reference="X"
            )
        )
        with pytest.raises(InvalidInput, match="n'appartient pas"):
            _pay_uc(services).execute(
                PayMerchantCommand(
                    payer_user_id=PAYER_ID,
                    merchant_id=other.merchant_id,
                    idempotency_key="mpay-key-xmerch",
                    charge_id=charge.charge_id,
                )
            )

    def test_charge_creation_validates_input(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _enroll(services, uow)
        with pytest.raises(InvalidInput, match="strictement positif"):
            CreateMerchantCharge(services=services).execute(
                CreateMerchantChargeCommand(
                    merchant_user_id=MERCHANT_ID, amount_minor=0, reference="X"
                )
            )
        with pytest.raises(InvalidInput, match="référence"):
            CreateMerchantCharge(services=services).execute(
                CreateMerchantChargeCommand(
                    merchant_user_id=MERCHANT_ID, amount_minor=100, reference="  "
                )
            )

    def test_charge_for_non_merchant_rejected(self, services: AppServices) -> None:
        with pytest.raises(NotAMerchant):
            CreateMerchantCharge(services=services).execute(
                CreateMerchantChargeCommand(
                    merchant_user_id=str(UUID(int=2)), amount_minor=100, reference="X"
                )
            )

    def test_expired_charge_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork, clock: FixedClock
    ) -> None:
        merchant_id = _enroll(services, uow)
        _user(uow, n=1, msisdn=PAYER_MSISDN, balance=100_000)
        charge = CreateMerchantCharge(services=services).execute(
            CreateMerchantChargeCommand(
                merchant_user_id=MERCHANT_ID, amount_minor=1_000, reference="X", ttl_minutes=10
            )
        )
        clock.advance(minutes=15)
        with pytest.raises(InvalidAccountState, match="expiré"):
            _pay_uc(services).execute(
                PayMerchantCommand(
                    payer_user_id=PAYER_ID,
                    merchant_id=merchant_id,
                    idempotency_key="mpay-key-exp",
                    charge_id=charge.charge_id,
                )
            )


class TestListing:
    def test_list_merchant_payments(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        merchant_id = _enroll(services, uow)
        _user(uow, n=1, msisdn=PAYER_MSISDN, balance=100_000)
        _pay_uc(services).execute(
            PayMerchantCommand(
                payer_user_id=PAYER_ID,
                merchant_id=merchant_id,
                idempotency_key="mpay-key-list1",
                amount_minor=10_000,
            )
        )
        lines = ListMerchantPayments(services=services).execute(
            ListMerchantPaymentsCommand(merchant_user_id=MERCHANT_ID)
        )
        assert [line.amount_minor for line in lines] == [10_000]
        assert lines[0].net_minor == 9_900

    def test_list_for_non_merchant_rejected(self, services: AppServices) -> None:
        with pytest.raises(NotAMerchant):
            ListMerchantPayments(services=services).execute(
                ListMerchantPaymentsCommand(merchant_user_id=str(UUID(int=2)))
            )
