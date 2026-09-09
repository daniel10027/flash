"""Cas d'usage de l'API marchande publique (BE-071)."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import pytest

from flash.application.merchants.api_keys import (
    IssueMerchantApiKey,
    IssueMerchantApiKeyCommand,
    RevokeMerchantApiKey,
    RevokeMerchantApiKeyCommand,
)
from flash.application.merchants.public_api import (
    AuthenticateMerchantApiKey,
    AuthenticateMerchantApiKeyCommand,
    GetMerchantChargeStatus,
    GetMerchantChargeStatusCommand,
)
from flash.application.services import AppServices
from flash.domain.merchants.charge import MerchantCharge
from flash.domain.merchants.merchant import Merchant
from flash.domain.merchants.payment import MerchantPayment
from flash.domain.shared.errors import InvalidInput, MerchantApiKeyInvalid
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import XOF, Money
from flash.infrastructure.merchant_api_keys import Sha256MerchantApiKeyVault
from tests.support.fakes import (
    FixedClock,
    InMemoryIdempotencyStore,
    RecordingEventPublisher,
    SeqIdGenerator,
)
from tests.support.repositories import InMemoryUnitOfWork

MID = EntityId(str(UUID(int=9)))
UID = str(UUID(int=9))
VAULT = Sha256MerchantApiKeyVault("test-pepper")


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


def _merchant(uow: InMemoryUnitOfWork, *, approved: bool = True, active: bool = True) -> None:
    merchant = Merchant.enroll(
        merchant_id=MID,
        user_id=EntityId(UID),
        display_name="Chez Awa",
        category="RESTAURANT",
        currency=XOF,
        fee_bps=100,
        now=FixedClock().now(),
    )
    if approved:
        merchant.approve_kyb(reviewer="r", now=FixedClock().now())
    if not active:
        merchant.suspend("fraude", FixedClock().now())
    merchant.pull_events()
    uow.merchants.add(merchant)


def _issue_key(services: AppServices) -> str:
    view = IssueMerchantApiKey(services=services, vault=VAULT).execute(
        IssueMerchantApiKeyCommand(merchant_user_id=UID, label="k")
    )
    return view.secret


class TestAuthenticate:
    def test_valid_key_returns_principal_and_marks_used(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _merchant(uow)
        secret = _issue_key(services)
        principal = AuthenticateMerchantApiKey(services=services, vault=VAULT).execute(
            AuthenticateMerchantApiKeyCommand(presented_secret=secret)
        )
        assert principal.merchant_id == str(MID)
        assert principal.merchant_user_id == UID
        assert principal.currency == "XOF"
        [key] = uow.merchant_api_keys.list_for_merchant(MID)
        assert key.last_used_at is not None

    def test_garbage_secret_rejected(self, services: AppServices) -> None:
        with pytest.raises(MerchantApiKeyInvalid):
            AuthenticateMerchantApiKey(services=services, vault=VAULT).execute(
                AuthenticateMerchantApiKeyCommand(presented_secret="not-a-key")
            )

    def test_unknown_prefix_rejected(self, services: AppServices) -> None:
        with pytest.raises(MerchantApiKeyInvalid):
            AuthenticateMerchantApiKey(services=services, vault=VAULT).execute(
                AuthenticateMerchantApiKeyCommand(presented_secret="mk_deadbeef_" + "z" * 32)
            )

    def test_wrong_secret_same_prefix_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _merchant(uow)
        secret = _issue_key(services)
        prefix = secret.split("_")[1]
        with pytest.raises(MerchantApiKeyInvalid):
            AuthenticateMerchantApiKey(services=services, vault=VAULT).execute(
                AuthenticateMerchantApiKeyCommand(presented_secret=f"mk_{prefix}_" + "0" * 32)
            )

    def test_revoked_key_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _merchant(uow)
        secret = _issue_key(services)
        [key] = uow.merchant_api_keys.list_for_merchant(MID)
        RevokeMerchantApiKey(services=services).execute(
            RevokeMerchantApiKeyCommand(merchant_user_id=UID, key_id=str(key.id))
        )
        with pytest.raises(MerchantApiKeyInvalid):
            AuthenticateMerchantApiKey(services=services, vault=VAULT).execute(
                AuthenticateMerchantApiKeyCommand(presented_secret=secret)
            )

    def test_kyb_not_approved_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _merchant(uow, approved=False)
        secret = _issue_key(services)
        with pytest.raises(MerchantApiKeyInvalid):
            AuthenticateMerchantApiKey(services=services, vault=VAULT).execute(
                AuthenticateMerchantApiKeyCommand(presented_secret=secret)
            )

    def test_suspended_merchant_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _merchant(uow, active=False)
        secret = _issue_key(services)
        with pytest.raises(MerchantApiKeyInvalid):
            AuthenticateMerchantApiKey(services=services, vault=VAULT).execute(
                AuthenticateMerchantApiKeyCommand(presented_secret=secret)
            )


class TestChargeStatus:
    def _charge(self, uow: InMemoryUnitOfWork) -> EntityId:
        charge = MerchantCharge.open(
            charge_id=EntityId(str(UUID(int=50))),
            merchant_id=MID,
            amount=Money(25_000, XOF),
            reference="Cmd 1",
            now=FixedClock().now(),
            expires_at=FixedClock().now() + timedelta(hours=1),
        )
        charge.pull_events()
        uow.merchant_charges.add(charge)
        return charge.id

    def test_pending_charge_has_no_payment(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _merchant(uow)
        charge_id = self._charge(uow)
        view = GetMerchantChargeStatus(services=services).execute(
            GetMerchantChargeStatusCommand(merchant_id=str(MID), charge_id=str(charge_id))
        )
        assert view.status == "PENDING"
        assert view.payment_id is None
        assert view.to_dict()["reference"] == "Cmd 1"

    def test_paid_charge_links_payment(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _merchant(uow)
        charge_id = self._charge(uow)
        txn_id = EntityId(str(UUID(int=77)))
        charge = uow.merchant_charges.get(charge_id)
        assert charge is not None
        charge.mark_paid(payer_id=EntityId(str(UUID(int=3))), ledger_transaction_id=txn_id)
        uow.merchant_charges.save(charge)
        payment = MerchantPayment.record(
            payment_id=EntityId(str(UUID(int=88))),
            payer_id=EntityId(str(UUID(int=3))),
            merchant_id=MID,
            amount=Money(25_000, XOF),
            fee=Money(250, XOF),
            reference="Cmd 1",
            ledger_transaction_id=txn_id,
            now=FixedClock().now(),
            charge_id=charge_id,
        )
        payment.pull_events()
        uow.merchant_payments.add(payment)

        view = GetMerchantChargeStatus(services=services).execute(
            GetMerchantChargeStatusCommand(merchant_id=str(MID), charge_id=str(charge_id))
        )
        assert view.payment_id == str(UUID(int=88))
        assert view.paid_at is not None

    def test_unknown_charge_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _merchant(uow)
        with pytest.raises(InvalidInput, match="introuvable"):
            GetMerchantChargeStatus(services=services).execute(
                GetMerchantChargeStatusCommand(
                    merchant_id=str(MID), charge_id=str(UUID(int=999))
                )
            )

    def test_malformed_charge_id_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _merchant(uow)
        with pytest.raises(InvalidInput, match="introuvable"):
            GetMerchantChargeStatus(services=services).execute(
                GetMerchantChargeStatusCommand(merchant_id=str(MID), charge_id="bad")
            )

    def test_charge_of_other_merchant_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _merchant(uow)
        charge_id = self._charge(uow)
        with pytest.raises(InvalidInput, match="introuvable"):
            GetMerchantChargeStatus(services=services).execute(
                GetMerchantChargeStatusCommand(
                    merchant_id=str(UUID(int=1234)), charge_id=str(charge_id)
                )
            )
