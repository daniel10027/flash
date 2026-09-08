"""Tests du relevé d'opérations (BE-038)."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import pytest

from flash.application.services import AppServices
from flash.application.statement.queries import (
    GetReceipt,
    GetReceiptCommand,
    ListStatement,
    ListStatementCommand,
)
from flash.application.transfers.reverse import CancelTransfer, CancelTransferCommand
from flash.application.transfers.send_p2p import (
    SendP2PTransfer,
    SendP2PTransferCommand,
    TransferReceipt,
)
from flash.domain.identity.pin import Pin
from flash.domain.identity.user import User
from flash.domain.limits.limits import KycPolicy, LimitPolicy
from flash.domain.pricing.pricing import PricingService
from flash.domain.shared.errors import WalletNotFound
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
A = "+2250700000001"
B = "+2250700000002"


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


def _account(uow: InMemoryUnitOfWork, *, n: int, msisdn: str, balance: int = 0) -> User:
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


def _transfer_r(
    services: AppServices, sender_id: str, amount: int, key: str, note: str | None = None
) -> TransferReceipt:
    return SendP2PTransfer(
        services=services,
        pricing=PricingService(build_pricing_repository()),
        limits=LimitPolicy(build_limit_repository(), NullLimitCounter()),
        kyc=KycPolicy(),
    ).execute(
        SendP2PTransferCommand(
            sender_user_id=sender_id,
            recipient_phone_number=B,
            amount_minor=amount,
            idempotency_key=key,
            country="CI",
            note=note,
        )
    )


def _transfer(
    services: AppServices, sender_id: str, amount: int, key: str, note: str | None = None
) -> None:
    _transfer_r(services, sender_id, amount, key, note)


class TestListStatement:
    def test_empty_when_no_activity(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        _account(uow, n=1, msisdn=A)
        page = ListStatement(services=services).execute(
            ListStatementCommand(user_id=str(UUID(int=1)))
        )
        assert page.lines == [] and page.next_cursor is None

    def test_outgoing_transfer_appears_as_out_with_fee_and_counterparty(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _account(uow, n=1, msisdn=A, balance=100_000)
        _account(uow, n=2, msisdn=B)
        _transfer(services, str(UUID(int=1)), 10_000, "k-out-0001", note="loyer")

        page = ListStatement(services=services).execute(
            ListStatementCommand(user_id=str(UUID(int=1)))
        )
        assert len(page.lines) == 1
        line = page.lines[0]
        assert line.direction == "out"
        assert line.kind == "TRANSFER"
        assert line.amount_minor == 10_000
        assert line.fee_minor == 80
        assert line.currency == "XOF"
        assert "***" in (line.counterparty_masked or "")
        assert line.note == "loyer"

    def test_incoming_transfer_appears_as_in_without_fee(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _account(uow, n=1, msisdn=A, balance=100_000)
        _account(uow, n=2, msisdn=B)
        _transfer(services, str(UUID(int=1)), 15_000, "k-in-00001")

        page = ListStatement(services=services).execute(
            ListStatementCommand(user_id=str(UUID(int=2)))
        )
        assert len(page.lines) == 1
        line = page.lines[0]
        assert line.direction == "in"
        assert line.amount_minor == 15_000
        assert line.fee_minor == 0

    def test_pagination_with_cursor(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        _account(uow, n=1, msisdn=A, balance=1_000_000)
        _account(uow, n=2, msisdn=B)
        for i in range(5):
            _transfer(services, str(UUID(int=1)), 1_000, f"k-page-{i}")

        first = ListStatement(services=services).execute(
            ListStatementCommand(user_id=str(UUID(int=1)), limit=2)
        )
        assert len(first.lines) == 2
        assert first.next_cursor is not None

        second = ListStatement(services=services).execute(
            ListStatementCommand(user_id=str(UUID(int=1)), limit=2, cursor=first.next_cursor)
        )
        assert len(second.lines) == 2
        # pas de recouvrement
        assert {line.id for line in first.lines} & {line.id for line in second.lines} == set()

        third = ListStatement(services=services).execute(
            ListStatementCommand(user_id=str(UUID(int=1)), limit=2, cursor=second.next_cursor)
        )
        assert len(third.lines) == 1
        assert third.next_cursor is None

    def test_limit_is_clamped(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        _account(uow, n=1, msisdn=A)
        page = ListStatement(services=services).execute(
            ListStatementCommand(user_id=str(UUID(int=1)), limit=99999)
        )
        assert page.lines == []

    def test_user_without_wallet_gets_empty_page(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        user = User.register(
            user_id=EntityId(str(UUID(int=7))),
            country=CI,
            msisdn=Msisdn("+2250700000007"),
            pin_hash="hashed:1397",
            now=FixedClock().now(),
        )
        user.pull_events()
        uow.users.add(user)
        page = ListStatement(services=services).execute(
            ListStatementCommand(user_id=str(UUID(int=7)))
        )
        assert page.lines == [] and page.next_cursor is None


class TestGetReceipt:
    def test_receipt_by_reference_from_sender_pov(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _account(uow, n=1, msisdn=A, balance=100_000)
        _account(uow, n=2, msisdn=B)
        r = _transfer_r(services, str(UUID(int=1)), 10_000, "rcpt-key-0001", note="loyer")

        receipt = GetReceipt(services=services).execute(
            GetReceiptCommand(user_id=str(UUID(int=1)), reference=r.reference)
        )
        assert receipt.direction == "out"
        assert receipt.amount_minor == 10_000
        assert receipt.fee_minor == 80
        assert receipt.status == "COMPLETED"
        assert receipt.reversed_at is None
        assert receipt.note == "loyer"
        assert "***" in (receipt.counterparty_masked or "")

    def test_receipt_by_transaction_id_from_recipient_pov(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _account(uow, n=1, msisdn=A, balance=100_000)
        _account(uow, n=2, msisdn=B)
        r = _transfer_r(services, str(UUID(int=1)), 10_000, "rcpt-key-0002")

        receipt = GetReceipt(services=services).execute(
            GetReceiptCommand(user_id=str(UUID(int=2)), reference=r.transfer_id)
        )
        assert receipt.direction == "in"
        assert receipt.amount_minor == 10_000
        assert receipt.fee_minor == 0

    def test_receipt_shows_reversed_status(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _account(uow, n=1, msisdn=A, balance=100_000)
        _account(uow, n=2, msisdn=B)
        r = _transfer_r(services, str(UUID(int=1)), 10_000, "rcpt-key-0003")
        CancelTransfer(services=services, window=timedelta(hours=1)).execute(
            CancelTransferCommand(
                actor_user_id=str(UUID(int=1)),
                transfer_id=r.transfer_id,
                idempotency_key="rcpt-rev-0003",
            )
        )
        receipt = GetReceipt(services=services).execute(
            GetReceiptCommand(user_id=str(UUID(int=1)), reference=r.reference)
        )
        assert receipt.status == "REVERSED"
        assert receipt.reversed_at is not None

    def test_receipt_for_merchant_payment_uses_merchant_name(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        from flash.application.merchants.operations import (
            EnrollMerchant,
            EnrollMerchantCommand,
            PayMerchant,
            PayMerchantCommand,
        )

        _account(uow, n=1, msisdn=A, balance=100_000)
        _account(uow, n=9, msisdn="+2250700000009")
        merchant = EnrollMerchant(services=services).execute(
            EnrollMerchantCommand(user_id=str(UUID(int=9)), display_name="Chez Awa")
        )
        pay = PayMerchant(
            services=services,
            limits=LimitPolicy(build_limit_repository(), NullLimitCounter()),
            kyc=KycPolicy(),
        ).execute(
            PayMerchantCommand(
                payer_user_id=str(UUID(int=1)),
                merchant_id=merchant.merchant_id,
                idempotency_key="rcpt-mpay-0001",
                amount_minor=25_000,
            )
        )
        receipt = GetReceipt(services=services).execute(
            GetReceiptCommand(user_id=str(UUID(int=1)), reference=f"MPY-{pay.payment_id}")
        )
        assert receipt.direction == "out"
        assert receipt.kind == "MERCHANT_PAYMENT"
        assert receipt.counterparty_masked == "Chez Awa"
        assert receipt.to_dict()["reference"] == f"MPY-{pay.payment_id}"

    def test_receipt_for_non_party_is_hidden(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _account(uow, n=1, msisdn=A, balance=100_000)
        _account(uow, n=2, msisdn=B)
        _account(uow, n=3, msisdn="+2250700000003")
        r = _transfer_r(services, str(UUID(int=1)), 10_000, "rcpt-key-0004")
        with pytest.raises(WalletNotFound):
            GetReceipt(services=services).execute(
                GetReceiptCommand(user_id=str(UUID(int=3)), reference=r.reference)
            )

    def test_receipt_unknown_reference_is_hidden(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _account(uow, n=1, msisdn=A, balance=100_000)
        with pytest.raises(WalletNotFound):
            GetReceipt(services=services).execute(
                GetReceiptCommand(user_id=str(UUID(int=1)), reference="TRX-nope")
            )
        with pytest.raises(WalletNotFound):
            GetReceipt(services=services).execute(
                GetReceiptCommand(user_id=str(UUID(int=1)), reference=str(UUID(int=987)))
            )

    def test_receipt_requires_a_wallet(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        user = User.register(
            user_id=EntityId(str(UUID(int=8))),
            country=CI,
            msisdn=Msisdn("+2250700000008"),
            pin_hash="hashed:1397",
            now=FixedClock().now(),
        )
        user.pull_events()
        uow.users.add(user)
        with pytest.raises(WalletNotFound):
            GetReceipt(services=services).execute(
                GetReceiptCommand(user_id=str(UUID(int=8)), reference="TRX-x")
            )
