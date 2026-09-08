"""Tests du cas d'usage SendP2PTransfer (BE-031)."""

from __future__ import annotations

from uuid import UUID

import pytest

from flash.application.services import AppServices
from flash.application.transfers.send_p2p import SendP2PTransfer, SendP2PTransferCommand
from flash.domain.identity.kyc import KycTier
from flash.domain.identity.pin import Pin
from flash.domain.identity.user import User
from flash.domain.ledger.chart import AccountType, Direction
from flash.domain.ledger.transaction import sum_postings
from flash.domain.limits.limits import KycPolicy, LimitPolicy
from flash.domain.pricing.pricing import PricingService
from flash.domain.shared.errors import (
    InsufficientFunds,
    InvalidInput,
    LimitExceeded,
    RecipientNotFound,
    SelfTransfer,
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


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


@pytest.fixture
def events() -> RecordingEventPublisher:
    return RecordingEventPublisher()


@pytest.fixture
def use_case(uow: InMemoryUnitOfWork, events: RecordingEventPublisher) -> SendP2PTransfer:
    services = AppServices(
        uow=lambda: uow,
        clock=FixedClock(),
        ids=SeqIdGenerator(),
        events=events,
        idempotency=InMemoryIdempotencyStore(),
    )
    return SendP2PTransfer(
        services=services,
        pricing=PricingService(build_pricing_repository()),
        limits=LimitPolicy(build_limit_repository(), NullLimitCounter()),
        kyc=KycPolicy(),
    )


def _account(
    uow: InMemoryUnitOfWork,
    *,
    tier: KycTier = KycTier.TIER_0,
    n: int,
    msisdn: str,
    balance: int = 0,
) -> User:
    user = User.register(
        user_id=EntityId(str(UUID(int=n))),
        country=CI,
        msisdn=Msisdn(msisdn),
        pin_hash=FakePinHasher().hash(Pin("1397")),
        now=FixedClock().now(),
    )
    user.activate(FixedClock().now())
    if tier is not KycTier.TIER_0:
        user.change_kyc_tier(tier, FixedClock().now())
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


def _cmd(**over: object) -> SendP2PTransferCommand:
    base: dict[str, object] = {
        "sender_user_id": str(UUID(int=1)),
        "recipient_phone_number": RECIPIENT,
        "amount_minor": 10_000,
        "idempotency_key": "trx-key-0001",
        "country": "CI",
    }
    base.update(over)
    return SendP2PTransferCommand(**base)  # type: ignore[arg-type]


class TestSendP2PTransfer:
    def test_happy_path_moves_money_and_charges_08_percent(
        self, use_case: SendP2PTransfer, uow: InMemoryUnitOfWork, events: RecordingEventPublisher
    ) -> None:
        _account(uow, n=1, msisdn=SENDER, balance=100_000)
        _account(uow, n=2, msisdn=RECIPIENT)

        receipt = use_case.execute(_cmd())

        assert receipt.amount_minor == 10_000
        assert receipt.fee_minor == 80  # 0,8 % de 10 000
        assert receipt.total_minor == 10_080
        assert receipt.currency == "XOF"
        assert receipt.sender_balance_after_minor == 100_000 - 10_080

        sender_wallet = uow.wallets.get_for_user(EntityId(str(UUID(int=1))), XOF)
        recipient_wallet = uow.wallets.get_for_user(EntityId(str(UUID(int=2))), XOF)
        assert sender_wallet.available == Money(89_920, XOF)  # type: ignore[union-attr]
        assert recipient_wallet.available == Money(10_000, XOF)  # type: ignore[union-attr]

        assert "TransferCompleted" in events.names()

    def test_ledger_transaction_is_balanced(
        self, use_case: SendP2PTransfer, uow: InMemoryUnitOfWork
    ) -> None:
        _account(uow, n=1, msisdn=SENDER, balance=50_000)
        _account(uow, n=2, msisdn=RECIPIENT)
        receipt = use_case.execute(_cmd(amount_minor=12_345))

        txns = uow.ledger.get_by_reference(receipt.reference)
        assert len(txns) == 1
        txn = txns[0]
        assert txn.is_balanced
        assert sum_postings(txn.postings) == {"XOF": 0}
        # débit émetteur = montant + frais
        debit = next(p for p in txn.postings if p.direction is Direction.DEBIT)
        assert debit.amount == Money(12_345 + 99, XOF)  # 0,8 % arrondi au sup.

    def test_fee_credited_to_flash_income(
        self, use_case: SendP2PTransfer, uow: InMemoryUnitOfWork
    ) -> None:
        _account(uow, n=1, msisdn=SENDER, balance=50_000)
        _account(uow, n=2, msisdn=RECIPIENT)
        receipt = use_case.execute(_cmd())
        txn = uow.ledger.get_by_reference(receipt.reference)[0]
        fee_account = uow.ledger.ensure_account(
            account_type=AccountType.FLASH_FEE_INCOME, currency=XOF
        )
        fee_posting = next(p for p in txn.postings if p.account_id == fee_account)
        assert fee_posting.direction is Direction.CREDIT
        assert fee_posting.amount == Money(80, XOF)

    def test_insufficient_funds_rejected(
        self, use_case: SendP2PTransfer, uow: InMemoryUnitOfWork
    ) -> None:
        _account(uow, n=1, msisdn=SENDER, balance=10_000)  # < 10 000 + 80
        _account(uow, n=2, msisdn=RECIPIENT)
        with pytest.raises(InsufficientFunds):
            use_case.execute(_cmd())

    def test_self_transfer_rejected(
        self, use_case: SendP2PTransfer, uow: InMemoryUnitOfWork
    ) -> None:
        _account(uow, n=1, msisdn=SENDER, balance=100_000)
        with pytest.raises(SelfTransfer):
            use_case.execute(_cmd(recipient_phone_number=SENDER))

    def test_unknown_recipient_rejected(
        self, use_case: SendP2PTransfer, uow: InMemoryUnitOfWork
    ) -> None:
        _account(uow, n=1, msisdn=SENDER, balance=100_000)
        with pytest.raises(RecipientNotFound):
            use_case.execute(_cmd())

    def test_recipient_without_wallet_in_currency_rejected(
        self, use_case: SendP2PTransfer, uow: InMemoryUnitOfWork
    ) -> None:
        _account(uow, n=1, msisdn=SENDER, balance=100_000)
        # destinataire enregistré mais sans portefeuille XOF
        recipient = User.register(
            user_id=EntityId(str(UUID(int=2))),
            country=CI,
            msisdn=Msisdn(RECIPIENT),
            pin_hash=FakePinHasher().hash(Pin("1397")),
            now=FixedClock().now(),
        )
        recipient.activate(FixedClock().now())
        recipient.pull_events()
        uow.users.add(recipient)
        with pytest.raises(RecipientNotFound):
            use_case.execute(_cmd())

    def test_amount_above_per_tx_limit_rejected(
        self, use_case: SendP2PTransfer, uow: InMemoryUnitOfWork
    ) -> None:
        _account(uow, n=1, msisdn=SENDER, balance=10_000_000)
        _account(uow, n=2, msisdn=RECIPIENT)
        # plafond tier 0 = 200 000
        with pytest.raises(LimitExceeded):
            use_case.execute(_cmd(amount_minor=250_000))

    def test_non_positive_amount_rejected(self, use_case: SendP2PTransfer) -> None:
        with pytest.raises(InvalidInput):
            use_case.execute(_cmd(amount_minor=0))

    def test_short_idempotency_key_rejected(self, use_case: SendP2PTransfer) -> None:
        with pytest.raises(InvalidInput):
            use_case.execute(_cmd(idempotency_key="x"))

    def test_idempotent_replay_does_not_double_charge(
        self, use_case: SendP2PTransfer, uow: InMemoryUnitOfWork
    ) -> None:
        _account(uow, n=1, msisdn=SENDER, balance=100_000)
        _account(uow, n=2, msisdn=RECIPIENT)
        first = use_case.execute(_cmd())
        second = use_case.execute(_cmd())
        assert first.transfer_id == second.transfer_id
        sender_wallet = uow.wallets.get_for_user(EntityId(str(UUID(int=1))), XOF)
        assert sender_wallet is not None
        assert sender_wallet.available == Money(89_920, XOF)  # un seul débit
