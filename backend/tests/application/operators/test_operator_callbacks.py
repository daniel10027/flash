"""Tests de la résolution des transferts opérateurs sur webhook (BE-067)."""

from __future__ import annotations

from uuid import UUID

import pytest

from flash.application.operators.callbacks import (
    HandleOperatorCallback,
    OperatorCallbackCommand,
)
from flash.application.operators.operations import (
    SendToOperatorAccount,
    SendToOperatorAccountCommand,
    TopUpFromOperator,
    TopUpFromOperatorCommand,
)
from flash.application.services import AppServices
from flash.domain.identity.pin import Pin
from flash.domain.identity.user import User
from flash.domain.ledger.transaction import TransactionKind, sum_postings
from flash.domain.limits.limits import KycPolicy, LimitPolicy
from flash.domain.pricing.pricing import PricingService
from flash.domain.shared.errors import InvalidInput
from flash.domain.shared.identifiers import CountryCode, EntityId, Msisdn
from flash.domain.shared.money import XOF, Money
from flash.domain.wallet.wallet import Wallet
from flash.infrastructure.limits import NullLimitCounter, build_limit_repository
from flash.infrastructure.operator_gateway import SandboxOperatorGateway
from flash.infrastructure.pricing import build_pricing_repository
from flash.infrastructure.reference import StaticReferenceDirectory
from tests.support.fakes import (
    FakePinHasher,
    FixedClock,
    InMemoryIdempotencyStore,
    RecordingEventPublisher,
    SeqIdGenerator,
)
from tests.support.repositories import InMemoryUnitOfWork

CI = CountryCode("CI")
USER_ID = str(UUID(int=1))
MSISDN = "+2250700000001"
TARGET = "+2250712345678"


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


def _user(uow: InMemoryUnitOfWork, *, balance: int) -> None:
    user = User.register(
        user_id=EntityId(USER_ID),
        country=CI,
        msisdn=Msisdn(MSISDN),
        pin_hash=FakePinHasher().hash(Pin("1397")),
        now=FixedClock().now(),
    )
    user.activate(FixedClock().now())
    user.pull_events()
    uow.users.add(user)
    wallet = Wallet.open(
        wallet_id=EntityId(str(UUID(int=500))),
        user_id=user.id,
        currency=XOF,
        now=FixedClock().now(),
    )
    wallet.credit(Money(balance, XOF), FixedClock().now())
    wallet.pull_events()
    uow.wallets.add(wallet)


def _kw(services: AppServices) -> dict[str, object]:
    return {
        "services": services,
        "gateway": SandboxOperatorGateway(pepper="t"),
        "reference": StaticReferenceDirectory(),
        "pricing": PricingService(build_pricing_repository()),
        "limits": LimitPolicy(build_limit_repository(), NullLimitCounter()),
        "kyc": KycPolicy(),
    }


def _start_payout(services: AppServices) -> str:
    return SendToOperatorAccount(**_kw(services)).execute(  # type: ignore[arg-type]
        SendToOperatorAccountCommand(
            user_id=USER_ID,
            operator="ORANGE_CI",
            msisdn=TARGET,
            amount_minor=50_000,
            idempotency_key="cb-payout-1",
        )
    ).reference


def _start_collect(services: AppServices) -> str:
    return TopUpFromOperator(**_kw(services)).execute(  # type: ignore[arg-type]
        TopUpFromOperatorCommand(
            user_id=USER_ID,
            operator="MTN_CI",
            msisdn=TARGET,
            amount_minor=30_000,
            idempotency_key="cb-collect-1",
        )
    ).reference


class TestPayoutCallback:
    def test_succeeded_settles_and_writes_ledger(
        self, services: AppServices, uow: InMemoryUnitOfWork, events: RecordingEventPublisher
    ) -> None:
        _user(uow, balance=100_000)
        ref = _start_payout(services)
        result = HandleOperatorCallback(services=services).execute(
            OperatorCallbackCommand(
                operator="ORANGE_CI", reference=ref, status="SUCCEEDED", external_ref="op_ext"
            )
        )
        assert result.status == "SUCCEEDED" and result.applied is True
        assert result.to_dict() == {
            "reference": ref,
            "status": "SUCCEEDED",
            "applied": True,
        }
        wallet = uow.wallets.get_for_user(EntityId(USER_ID), XOF)
        assert wallet is not None
        assert wallet.reserved == Money(0, XOF) and wallet.balance == Money(49_250, XOF)
        [txn] = uow.ledger.transactions
        assert txn.kind is TransactionKind.OPERATOR_PAYOUT
        assert txn.is_balanced and sum_postings(txn.postings) == {"XOF": 0}
        assert "OperatorTransferSucceeded" in events.names()

    def test_failed_releases_reservation(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=100_000)
        ref = _start_payout(services)
        HandleOperatorCallback(services=services).execute(
            OperatorCallbackCommand(
                operator="ORANGE_CI", reference=ref, status="FAILED", reason="OPERATOR_TIMEOUT"
            )
        )
        wallet = uow.wallets.get_for_user(EntityId(USER_ID), XOF)
        assert wallet is not None
        assert wallet.available == Money(100_000, XOF) and wallet.reserved == Money(0, XOF)
        assert uow.ledger.transactions == []

    def test_replay_is_noop(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        _user(uow, balance=100_000)
        ref = _start_payout(services)
        cmd = OperatorCallbackCommand(operator="ORANGE_CI", reference=ref, status="SUCCEEDED")
        first = HandleOperatorCallback(services=services).execute(cmd)
        second = HandleOperatorCallback(services=services).execute(cmd)
        assert first.applied is True and second.applied is False
        assert len(uow.ledger.transactions) == 1


class TestCollectCallback:
    def test_succeeded_credits_wallet_net_of_fee(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=1_000)
        ref = _start_collect(services)
        HandleOperatorCallback(services=services).execute(
            OperatorCallbackCommand(operator="MTN_CI", reference=ref, status="SUCCEEDED")
        )
        wallet = uow.wallets.get_for_user(EntityId(USER_ID), XOF)
        assert wallet is not None
        assert wallet.available == Money(1_000 + 30_000 - 300, XOF)
        [txn] = uow.ledger.transactions
        assert txn.kind is TransactionKind.OPERATOR_COLLECT
        assert txn.is_balanced and sum_postings(txn.postings) == {"XOF": 0}

    def test_failed_leaves_wallet_untouched(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=1_000)
        ref = _start_collect(services)
        HandleOperatorCallback(services=services).execute(
            OperatorCallbackCommand(operator="MTN_CI", reference=ref, status="FAILED", reason="KO")
        )
        wallet = uow.wallets.get_for_user(EntityId(USER_ID), XOF)
        assert wallet is not None and wallet.available == Money(1_000, XOF)
        assert uow.ledger.transactions == []


class TestCallbackErrors:
    def test_unknown_reference_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=1_000)
        with pytest.raises(InvalidInput, match="introuvable"):
            HandleOperatorCallback(services=services).execute(
                OperatorCallbackCommand(
                    operator="ORANGE_CI", reference="OPO-nope", status="SUCCEEDED"
                )
            )

    def test_operator_mismatch_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=100_000)
        ref = _start_payout(services)
        with pytest.raises(InvalidInput, match="émetteur"):
            HandleOperatorCallback(services=services).execute(
                OperatorCallbackCommand(operator="MTN_CI", reference=ref, status="SUCCEEDED")
            )

    def test_bad_status_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=100_000)
        ref = _start_payout(services)
        with pytest.raises(InvalidInput, match="Statut"):
            HandleOperatorCallback(services=services).execute(
                OperatorCallbackCommand(operator="ORANGE_CI", reference=ref, status="MAYBE")
            )
