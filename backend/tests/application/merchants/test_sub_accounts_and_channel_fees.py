"""Cas d'usage : caisses / employés + frais négociés par canal (reste de BE-068)."""

from __future__ import annotations

from uuid import UUID

import pytest

from flash.application.merchants.channel_fees import (
    ClearMerchantChannelFee,
    ClearMerchantChannelFeeCommand,
    GetMerchantFees,
    GetMerchantFeesCommand,
    SetMerchantChannelFee,
    SetMerchantChannelFeeCommand,
)
from flash.application.merchants.operations import (
    CreateMerchantCharge,
    CreateMerchantChargeCommand,
    EnrollMerchant,
    EnrollMerchantCommand,
    ListMerchantPayments,
    ListMerchantPaymentsCommand,
    NotAMerchant,
    PayMerchant,
    PayMerchantCommand,
)
from flash.application.merchants.sub_accounts import (
    CreateSubAccount,
    CreateSubAccountCommand,
    ListSubAccounts,
    ListSubAccountsCommand,
    UpdateSubAccount,
    UpdateSubAccountCommand,
)
from flash.application.services import AppServices
from flash.domain.identity.pin import Pin
from flash.domain.identity.user import User
from flash.domain.limits.limits import KycPolicy, LimitPolicy
from flash.domain.merchants.merchant import PaymentChannel
from flash.domain.shared.errors import InvalidInput
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
MERCHANT_ID = str(UUID(int=9))
PAYER_ID = str(UUID(int=1))


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
    _user(uow, n=9, msisdn="+2250700000009")
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


class TestSubAccounts:
    def test_create_list_update(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _enroll(services, uow)
        created = CreateSubAccount(services=services).execute(
            CreateSubAccountCommand(
                merchant_user_id=MERCHANT_ID, kind="till", label="Caisse 1"
            )
        )
        assert created.kind == "TILL" and created.active is True

        CreateSubAccount(services=services).execute(
            CreateSubAccountCommand(
                merchant_user_id=MERCHANT_ID, kind="EMPLOYEE", label="Awa"
            )
        )
        listed = ListSubAccounts(services=services).execute(
            ListSubAccountsCommand(merchant_user_id=MERCHANT_ID)
        )
        assert [s.label for s in listed] == ["Caisse 1", "Awa"]

        UpdateSubAccount(services=services).execute(
            UpdateSubAccountCommand(
                merchant_user_id=MERCHANT_ID,
                sub_account_id=created.id,
                label="Caisse principale",
                active=False,
            )
        )
        active_only = ListSubAccounts(services=services).execute(
            ListSubAccountsCommand(merchant_user_id=MERCHANT_ID, include_inactive=False)
        )
        assert [s.label for s in active_only] == ["Awa"]

    def test_create_for_non_merchant_rejected(self, services: AppServices) -> None:
        with pytest.raises(NotAMerchant):
            CreateSubAccount(services=services).execute(
                CreateSubAccountCommand(
                    merchant_user_id=str(UUID(int=404)), kind="TILL", label="x"
                )
            )

    def test_bad_kind_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _enroll(services, uow)
        with pytest.raises(InvalidInput, match="TILL"):
            CreateSubAccount(services=services).execute(
                CreateSubAccountCommand(
                    merchant_user_id=MERCHANT_ID, kind="ROBOT", label="x"
                )
            )

    def test_update_foreign_sub_account_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _enroll(services, uow)
        with pytest.raises(InvalidInput, match="introuvable"):
            UpdateSubAccount(services=services).execute(
                UpdateSubAccountCommand(
                    merchant_user_id=MERCHANT_ID,
                    sub_account_id=str(UUID(int=777)),
                    label="x",
                )
            )

    def test_update_malformed_id_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _enroll(services, uow)
        with pytest.raises(InvalidInput, match="invalide"):
            UpdateSubAccount(services=services).execute(
                UpdateSubAccountCommand(
                    merchant_user_id=MERCHANT_ID, sub_account_id="nope", label="x"
                )
            )

    def test_list_and_update_for_non_merchant_rejected(
        self, services: AppServices
    ) -> None:
        with pytest.raises(NotAMerchant):
            ListSubAccounts(services=services).execute(
                ListSubAccountsCommand(merchant_user_id=str(UUID(int=404)))
            )
        with pytest.raises(NotAMerchant):
            UpdateSubAccount(services=services).execute(
                UpdateSubAccountCommand(
                    merchant_user_id=str(UUID(int=404)),
                    sub_account_id=str(UUID(int=1)),
                    label="x",
                )
            )

    def test_max_sub_accounts_enforced(
        self,
        services: AppServices,
        uow: InMemoryUnitOfWork,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        import flash.application.merchants.sub_accounts as mod

        monkeypatch.setattr(mod, "_MAX_SUB_ACCOUNTS", 1)
        _enroll(services, uow)
        CreateSubAccount(services=services).execute(
            CreateSubAccountCommand(
                merchant_user_id=MERCHANT_ID, kind="TILL", label="Caisse 1"
            )
        )
        with pytest.raises(InvalidInput, match="Nombre maximum"):
            CreateSubAccount(services=services).execute(
                CreateSubAccountCommand(
                    merchant_user_id=MERCHANT_ID, kind="TILL", label="Caisse 2"
                )
            )


class TestPaymentAttribution:
    def test_static_qr_payment_carries_sub_account_and_is_listed(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _enroll(services, uow)
        _user(uow, n=1, msisdn="+2250700000001", balance=100_000)
        till = CreateSubAccount(services=services).execute(
            CreateSubAccountCommand(
                merchant_user_id=MERCHANT_ID, kind="TILL", label="Caisse 1"
            )
        )
        _pay_uc(services).execute(
            PayMerchantCommand(
                payer_user_id=PAYER_ID,
                merchant_id=_merchant_id(uow),
                idempotency_key="idem-key-static-1",
                amount_minor=10_000,
                sub_account_id=till.id,
            )
        )
        lines = ListMerchantPayments(services=services).execute(
            ListMerchantPaymentsCommand(
                merchant_user_id=MERCHANT_ID, sub_account_id=till.id
            )
        )
        assert len(lines) == 1 and lines[0].sub_account_id == till.id
        assert (
            ListMerchantPayments(services=services)
            .execute(
                ListMerchantPaymentsCommand(
                    merchant_user_id=MERCHANT_ID, sub_account_id=str(UUID(int=888))
                )
            )
            == []
        )

    def test_charge_sub_account_is_inherited_by_payment(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _enroll(services, uow)
        _user(uow, n=1, msisdn="+2250700000001", balance=100_000)
        emp = CreateSubAccount(services=services).execute(
            CreateSubAccountCommand(
                merchant_user_id=MERCHANT_ID, kind="EMPLOYEE", label="Awa"
            )
        )
        charge = CreateMerchantCharge(services=services).execute(
            CreateMerchantChargeCommand(
                merchant_user_id=MERCHANT_ID,
                amount_minor=5_000,
                reference="T4",
                sub_account_id=emp.id,
            )
        )
        _pay_uc(services).execute(
            PayMerchantCommand(
                payer_user_id=PAYER_ID,
                merchant_id=_merchant_id(uow),
                idempotency_key="idem-key-charge-2",
                charge_id=charge.charge_id,
            )
        )
        lines = ListMerchantPayments(services=services).execute(
            ListMerchantPaymentsCommand(merchant_user_id=MERCHANT_ID)
        )
        assert lines[0].sub_account_id == emp.id

    def test_unknown_sub_account_id_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _enroll(services, uow)
        _user(uow, n=1, msisdn="+2250700000001", balance=100_000)
        with pytest.raises(InvalidInput, match="n'appartient pas"):
            _pay_uc(services).execute(
                PayMerchantCommand(
                    payer_user_id=PAYER_ID,
                    merchant_id=_merchant_id(uow),
                    idempotency_key="idem-key-unknown-sa",
                    amount_minor=1_000,
                    sub_account_id=str(UUID(int=999)),
                )
            )

    def test_malformed_sub_account_id_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _enroll(services, uow)
        _user(uow, n=1, msisdn="+2250700000001", balance=100_000)
        with pytest.raises(InvalidInput, match="invalide"):
            _pay_uc(services).execute(
                PayMerchantCommand(
                    payer_user_id=PAYER_ID,
                    merchant_id=_merchant_id(uow),
                    idempotency_key="idem-key-bad-sa-id",
                    amount_minor=1_000,
                    sub_account_id="not-a-uuid",
                )
            )

    def test_deactivated_sub_account_refuses_payment(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _enroll(services, uow)
        _user(uow, n=1, msisdn="+2250700000001", balance=100_000)
        till = CreateSubAccount(services=services).execute(
            CreateSubAccountCommand(
                merchant_user_id=MERCHANT_ID, kind="TILL", label="Caisse 1"
            )
        )
        UpdateSubAccount(services=services).execute(
            UpdateSubAccountCommand(
                merchant_user_id=MERCHANT_ID, sub_account_id=till.id, active=False
            )
        )
        with pytest.raises(InvalidInput, match="désactivé"):
            _pay_uc(services).execute(
                PayMerchantCommand(
                    payer_user_id=PAYER_ID,
                    merchant_id=_merchant_id(uow),
                    idempotency_key="idem-key-deact-3",
                    amount_minor=1_000,
                    sub_account_id=till.id,
                )
            )


class TestChannelFees:
    def test_set_get_clear(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        merchant_id = _enroll(services, uow, fee_bps=80)
        view = SetMerchantChannelFee(services=services).execute(
            SetMerchantChannelFeeCommand(
                merchant_id=merchant_id, channel="api", fee_bps=150
            )
        )
        assert view.channel_fees == {"API": 150} and view.default_fee_bps == 80
        got = GetMerchantFees(services=services).execute(
            GetMerchantFeesCommand(merchant_id=merchant_id)
        )
        assert got.channel_fees == {"API": 150}
        cleared = ClearMerchantChannelFee(services=services).execute(
            ClearMerchantChannelFeeCommand(merchant_id=merchant_id, channel="API")
        )
        assert cleared.channel_fees == {}

    def test_negotiated_fee_applies_to_api_channel_payment(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        merchant_id = _enroll(services, uow, fee_bps=80)
        _user(uow, n=1, msisdn="+2250700000001", balance=100_000)
        SetMerchantChannelFee(services=services).execute(
            SetMerchantChannelFeeCommand(
                merchant_id=merchant_id, channel="API", fee_bps=200
            )
        )
        charge = CreateMerchantCharge(services=services).execute(
            CreateMerchantChargeCommand(
                merchant_user_id=MERCHANT_ID,
                amount_minor=10_000,
                reference="api-1",
                channel=PaymentChannel.API,
            )
        )
        receipt = _pay_uc(services).execute(
            PayMerchantCommand(
                payer_user_id=PAYER_ID,
                merchant_id=merchant_id,
                idempotency_key="idem-key-api-fee",
                charge_id=charge.charge_id,
            )
        )
        assert receipt.fee_minor == 200  # 2 % négocié, pas les 0,8 % par défaut

    def test_default_fee_still_applies_to_qr(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        merchant_id = _enroll(services, uow, fee_bps=80)
        _user(uow, n=1, msisdn="+2250700000001", balance=100_000)
        SetMerchantChannelFee(services=services).execute(
            SetMerchantChannelFeeCommand(
                merchant_id=merchant_id, channel="API", fee_bps=200
            )
        )
        receipt = _pay_uc(services).execute(
            PayMerchantCommand(
                payer_user_id=PAYER_ID,
                merchant_id=merchant_id,
                idempotency_key="idem-key-qr-default",
                amount_minor=10_000,
            )
        )
        assert receipt.fee_minor == 80

    def test_set_for_unknown_merchant_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput, match="introuvable"):
            SetMerchantChannelFee(services=services).execute(
                SetMerchantChannelFeeCommand(
                    merchant_id=str(UUID(int=404)), channel="API", fee_bps=100
                )
            )

    def test_set_for_malformed_merchant_id_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput, match="introuvable"):
            SetMerchantChannelFee(services=services).execute(
                SetMerchantChannelFeeCommand(
                    merchant_id="not-a-uuid", channel="API", fee_bps=100
                )
            )

    def test_bad_channel_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        merchant_id = _enroll(services, uow)
        with pytest.raises(InvalidInput, match="Canal attendu"):
            SetMerchantChannelFee(services=services).execute(
                SetMerchantChannelFeeCommand(
                    merchant_id=merchant_id, channel="SMS", fee_bps=100
                )
            )


def _merchant_id(uow: InMemoryUnitOfWork) -> str:
    merchant = uow.merchants.get_by_user_id(EntityId(MERCHANT_ID))
    assert merchant is not None
    return str(merchant.id)
