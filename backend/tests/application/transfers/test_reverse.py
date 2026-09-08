"""Tests de CancelTransfer (BE-037) — annulation d'un transfert par contre-passation."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import pytest

from flash.application.services import AppServices
from flash.application.transfers.reverse import CancelTransfer, CancelTransferCommand
from flash.application.transfers.send_p2p import SendP2PTransfer, SendP2PTransferCommand
from flash.domain.identity.pin import Pin
from flash.domain.identity.user import User
from flash.domain.ledger.transaction import TransactionKind
from flash.domain.limits.limits import KycPolicy, LimitPolicy
from flash.domain.pricing.pricing import PricingService
from flash.domain.shared.errors import (
    DuplicateOperation,
    InvalidInput,
    RefundNotPossible,
    ReversalWindowClosed,
)
from flash.domain.shared.identifiers import CountryCode, EntityId, Msisdn
from flash.domain.shared.money import XOF, Money
from flash.domain.wallet.wallet import Wallet
from flash.infrastructure.limits import NullLimitCounter, build_limit_repository
from flash.infrastructure.pricing import build_pricing_repository
from tests.support.fakes import (
    FakePinHasher,
    FixedClock,
    InMemoryIdempotencyStore,
    RecordingEventPublisher,
    SeqIdGenerator,
)
from tests.support.repositories import InMemoryUnitOfWork

CI = CountryCode("CI")
SENDER = "+2250700000001"
RECIPIENT = "+2250700000002"
SENDER_ID = str(UUID(int=1))
RECIPIENT_ID = str(UUID(int=2))
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


@pytest.fixture
def transfers(services: AppServices) -> SendP2PTransfer:
    return SendP2PTransfer(
        services=services,
        pricing=PricingService(build_pricing_repository()),
        limits=LimitPolicy(build_limit_repository(), NullLimitCounter()),
        kyc=KycPolicy(),
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
        wallet_id=EntityId(str(UUID(int=100 + n))),
        user_id=user.id,
        currency=XOF,
        now=FixedClock().now(),
    )
    if balance:
        wallet.credit(Money(balance, XOF), FixedClock().now())
    wallet.pull_events()
    uow.wallets.add(wallet)
    return user


def _send(transfers: SendP2PTransfer, amount: int = 10_000) -> str:
    receipt = transfers.execute(
        SendP2PTransferCommand(
            sender_user_id=SENDER_ID,
            recipient_phone_number=RECIPIENT,
            amount_minor=amount,
            idempotency_key="trx-key-0001",
            country="CI",
        )
    )
    return receipt.transfer_id


def _cancel_uc(services: AppServices) -> CancelTransfer:
    return CancelTransfer(services=services, window=WINDOW)


class TestCancelTransfer:
    def test_cancel_restores_balances_and_adds_reversal(
        self, services: AppServices, uow: InMemoryUnitOfWork, transfers: SendP2PTransfer
    ) -> None:
        _user(uow, n=1, msisdn=SENDER, balance=100_000)
        _user(uow, n=2, msisdn=RECIPIENT)
        transfer_id = _send(transfers, 10_000)  # frais 0,8 % = 80

        receipt = _cancel_uc(services).execute(
            CancelTransferCommand(
                actor_user_id=SENDER_ID, transfer_id=transfer_id, idempotency_key="rev-key-0001"
            )
        )
        assert receipt.amount_minor == 10_000
        assert receipt.fee_minor == 80
        assert receipt.sender_balance_after_minor == 100_000  # tout est revenu

        sender_wallet = uow.wallets.get_for_user(EntityId(SENDER_ID), XOF)
        recipient_wallet = uow.wallets.get_for_user(EntityId(RECIPIENT_ID), XOF)
        assert sender_wallet is not None and recipient_wallet is not None
        assert sender_wallet.available == Money(100_000, XOF)
        assert recipient_wallet.available == Money(0, XOF)

        txns = uow.ledger.get_by_reference(receipt.reference)
        kinds = sorted(t.kind for t in txns)
        assert kinds == sorted([TransactionKind.TRANSFER, TransactionKind.REVERSAL])
        assert all(t.is_balanced for t in txns)

    def test_only_sender_can_cancel(
        self, services: AppServices, uow: InMemoryUnitOfWork, transfers: SendP2PTransfer
    ) -> None:
        _user(uow, n=1, msisdn=SENDER, balance=100_000)
        _user(uow, n=2, msisdn=RECIPIENT)
        transfer_id = _send(transfers)
        with pytest.raises(InvalidInput, match="introuvable"):
            _cancel_uc(services).execute(
                CancelTransferCommand(
                    actor_user_id=RECIPIENT_ID,
                    transfer_id=transfer_id,
                    idempotency_key="rev-key-wrong",
                )
            )

    def test_cannot_cancel_twice(
        self, services: AppServices, uow: InMemoryUnitOfWork, transfers: SendP2PTransfer
    ) -> None:
        _user(uow, n=1, msisdn=SENDER, balance=100_000)
        _user(uow, n=2, msisdn=RECIPIENT)
        transfer_id = _send(transfers)
        _cancel_uc(services).execute(
            CancelTransferCommand(
                actor_user_id=SENDER_ID, transfer_id=transfer_id, idempotency_key="rev-key-a"
            )
        )
        with pytest.raises(DuplicateOperation):
            _cancel_uc(services).execute(
                CancelTransferCommand(
                    actor_user_id=SENDER_ID, transfer_id=transfer_id, idempotency_key="rev-key-b"
                )
            )

    def test_window_closed_rejected(
        self,
        services: AppServices,
        uow: InMemoryUnitOfWork,
        transfers: SendP2PTransfer,
        clock: FixedClock,
    ) -> None:
        _user(uow, n=1, msisdn=SENDER, balance=100_000)
        _user(uow, n=2, msisdn=RECIPIENT)
        transfer_id = _send(transfers)
        clock.advance(hours=2)
        with pytest.raises(ReversalWindowClosed):
            _cancel_uc(services).execute(
                CancelTransferCommand(
                    actor_user_id=SENDER_ID, transfer_id=transfer_id, idempotency_key="rev-key-old"
                )
            )

    def test_refund_not_possible_when_recipient_spent(
        self, services: AppServices, uow: InMemoryUnitOfWork, transfers: SendP2PTransfer
    ) -> None:
        _user(uow, n=1, msisdn=SENDER, balance=100_000)
        _user(uow, n=2, msisdn=RECIPIENT)
        transfer_id = _send(transfers, 10_000)
        # le destinataire dépense ce qu'il a reçu
        recipient_wallet = uow.wallets.get_for_user(EntityId(RECIPIENT_ID), XOF)
        assert recipient_wallet is not None
        recipient_wallet.debit(Money(10_000, XOF), FixedClock().now())
        recipient_wallet.pull_events()
        with pytest.raises(RefundNotPossible):
            _cancel_uc(services).execute(
                CancelTransferCommand(
                    actor_user_id=SENDER_ID,
                    transfer_id=transfer_id,
                    idempotency_key="rev-key-spent",
                )
            )

    def test_same_key_replays_receipt(
        self, services: AppServices, uow: InMemoryUnitOfWork, transfers: SendP2PTransfer
    ) -> None:
        _user(uow, n=1, msisdn=SENDER, balance=100_000)
        _user(uow, n=2, msisdn=RECIPIENT)
        transfer_id = _send(transfers)
        uc = _cancel_uc(services)
        cmd = CancelTransferCommand(
            actor_user_id=SENDER_ID, transfer_id=transfer_id, idempotency_key="rev-key-rep"
        )
        assert uc.execute(cmd) == uc.execute(cmd)

    def test_unknown_transfer_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput, match="introuvable"):
            _cancel_uc(services).execute(
                CancelTransferCommand(
                    actor_user_id=SENDER_ID,
                    transfer_id=str(UUID(int=999)),
                    idempotency_key="rev-key-none",
                )
            )

    def test_bad_idempotency_key_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput):
            _cancel_uc(services).execute(
                CancelTransferCommand(
                    actor_user_id=SENDER_ID, transfer_id=str(UUID(int=1)), idempotency_key="x"
                )
            )
