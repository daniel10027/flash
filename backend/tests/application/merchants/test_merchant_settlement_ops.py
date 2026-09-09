"""Tests des cas d'usage de règlement marchand (BE-070) : configuration, déclenchement
manuel, relevé, et la fonction partagée ``settle_merchant``."""

from __future__ import annotations

from uuid import UUID

import pytest

from flash.application.merchants.bank import BankAck
from flash.application.merchants.operations import NotAMerchant
from flash.application.merchants.settlement import (
    ConfigureMerchantSettlement,
    ConfigureMerchantSettlementCommand,
    GetSettlementStatement,
    GetSettlementStatementCommand,
    ListMerchantSettlements,
    ListMerchantSettlementsCommand,
    SettleMerchantNow,
    SettleMerchantNowCommand,
    settle_merchant,
)
from flash.application.services import AppServices
from flash.domain.ledger.transaction import TransactionKind, sum_postings
from flash.domain.merchants.merchant import Merchant
from flash.domain.merchants.payment import MerchantPayment, MerchantPaymentStatus
from flash.domain.shared.errors import InvalidInput
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import XOF, Money
from tests.support.fakes import (
    FixedClock,
    InMemoryIdempotencyStore,
    RecordingEventPublisher,
    SeqIdGenerator,
)
from tests.support.repositories import InMemoryUnitOfWork

MERCHANT_ID = EntityId(str(UUID(int=9)))
MERCHANT_USER_ID = str(UUID(int=9))
PAYER_ID = EntityId(str(UUID(int=1)))
IBAN = "CI93CI0080111301134291200589"


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
def events() -> RecordingEventPublisher:
    return RecordingEventPublisher()


@pytest.fixture
def services(
    uow: InMemoryUnitOfWork, clock: FixedClock, events: RecordingEventPublisher
) -> AppServices:
    return AppServices(
        uow=lambda: uow,
        clock=clock,
        ids=SeqIdGenerator(),
        events=events,
        idempotency=InMemoryIdempotencyStore(),
    )


class _Bank:
    def transfer(self, **_: object) -> BankAck:
        return BankAck(accepted=True, bank_reference="bank_ref_001")


def _merchant(uow: InMemoryUnitOfWork, *, fee_bps: int = 100) -> Merchant:
    merchant = Merchant.enroll(
        merchant_id=MERCHANT_ID,
        user_id=EntityId(MERCHANT_USER_ID),
        display_name="Chez Awa",
        category="RESTAURANT",
        currency=XOF,
        fee_bps=fee_bps,
        now=FixedClock().now(),
    )
    merchant.pull_events()
    uow.merchants.add(merchant)
    return merchant


def _payment(uow: InMemoryUnitOfWork, *, n: int, amount: int, fee: int) -> MerchantPayment:
    payment = MerchantPayment.record(
        payment_id=EntityId(str(UUID(int=100 + n))),
        payer_id=PAYER_ID,
        merchant_id=MERCHANT_ID,
        amount=Money(amount, XOF),
        fee=Money(fee, XOF),
        reference=f"Table {n}",
        ledger_transaction_id=EntityId(str(UUID(int=900 + n))),
        now=FixedClock().now(),
    )
    payment.pull_events()
    uow.merchant_payments.add(payment)
    return payment


def _configure(
    services: AppServices, *, frequency: str = "MANUAL"
) -> None:
    ConfigureMerchantSettlement(services=services).execute(
        ConfigureMerchantSettlementCommand(
            merchant_user_id=MERCHANT_USER_ID,
            holder="SARL Chez Awa",
            iban=IBAN,
            bank_name="Ecobank CI",
            frequency=frequency,
        )
    )


class TestConfigure:
    def test_configure_sets_bank_account_and_schedule(
        self, services: AppServices, uow: InMemoryUnitOfWork, events: RecordingEventPublisher
    ) -> None:
        _merchant(uow)
        view = ConfigureMerchantSettlement(services=services).execute(
            ConfigureMerchantSettlementCommand(
                merchant_user_id=MERCHANT_USER_ID,
                holder="SARL Chez Awa",
                iban=IBAN,
                bank_name="Ecobank CI",
                frequency="WEEKLY",
            )
        )
        assert view.frequency == "WEEKLY"
        assert view.bank_iban_masked == "CI93…0589"
        assert view.next_settlement_at is not None
        merchant = uow.merchants.get(MERCHANT_ID)
        assert merchant is not None and merchant.bank_account is not None
        assert "MerchantSettlementConfigured" in events.names()

    def test_configure_manual_has_no_next_date(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _merchant(uow)
        view = ConfigureMerchantSettlement(services=services).execute(
            ConfigureMerchantSettlementCommand(
                merchant_user_id=MERCHANT_USER_ID,
                holder="SARL Chez Awa",
                iban=IBAN,
                bank_name="Ecobank CI",
            )
        )
        assert view.frequency == "MANUAL"
        assert view.next_settlement_at is None

    def test_unknown_frequency_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput, match="Fréquence"):
            ConfigureMerchantSettlement(services=services).execute(
                ConfigureMerchantSettlementCommand(
                    merchant_user_id=MERCHANT_USER_ID,
                    holder="Awa",
                    iban=IBAN,
                    bank_name="Ecobank",
                    frequency="HOURLY",
                )
            )

    def test_invalid_iban_rejected(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput, match="IBAN"):
            ConfigureMerchantSettlement(services=services).execute(
                ConfigureMerchantSettlementCommand(
                    merchant_user_id=MERCHANT_USER_ID,
                    holder="Awa",
                    iban="short",
                    bank_name="Ecobank",
                )
            )

    def test_non_merchant_rejected(self, services: AppServices) -> None:
        with pytest.raises(NotAMerchant):
            _configure(services)


class TestSettleMerchantNow:
    def test_settles_net_and_writes_ledger(
        self, services: AppServices, uow: InMemoryUnitOfWork, events: RecordingEventPublisher
    ) -> None:
        _merchant(uow)
        _payment(uow, n=1, amount=10_000, fee=100)
        _payment(uow, n=2, amount=5_000, fee=50)
        _configure(services)

        view = SettleMerchantNow(services=services, bank=_Bank()).execute(
            SettleMerchantNowCommand(merchant_user_id=MERCHANT_USER_ID)
        )
        assert view is not None
        assert view.status == "PAID"
        assert view.amount_minor == 10_000 - 100 + 5_000 - 50
        assert view.payment_count == 2
        assert view.bank_reference == "bank_ref_001"

        txns = uow.ledger.transactions
        assert len(txns) == 1
        assert txns[0].kind is TransactionKind.MERCHANT_SETTLEMENT
        assert sum_postings(txns[0].postings) == {"XOF": 0}

        for payment in uow.merchant_payments.list_for_merchant(MERCHANT_ID):
            assert payment.settlement_id is not None
        assert "MerchantSettlementPaid" in events.names()

    def test_returns_none_when_nothing_to_settle(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _merchant(uow)
        _configure(services)
        view = SettleMerchantNow(services=services, bank=_Bank()).execute(
            SettleMerchantNowCommand(merchant_user_id=MERCHANT_USER_ID)
        )
        assert view is None
        assert uow.ledger.transactions == []

    def test_no_bank_account_configured_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _merchant(uow)
        _payment(uow, n=1, amount=10_000, fee=100)
        with pytest.raises(InvalidInput, match="bancaire"):
            SettleMerchantNow(services=services, bank=_Bank()).execute(
                SettleMerchantNowCommand(merchant_user_id=MERCHANT_USER_ID)
            )

    def test_bank_rejection_marks_failed_and_keeps_payments_open(
        self, services: AppServices, uow: InMemoryUnitOfWork, events: RecordingEventPublisher
    ) -> None:
        _merchant(uow)
        _payment(uow, n=1, amount=10_000, fee=100)
        _configure(services)

        view = SettleMerchantNow(services=services, bank=_RejectingBank()).execute(
            SettleMerchantNowCommand(merchant_user_id=MERCHANT_USER_ID)
        )
        assert view is not None and view.status == "FAILED"
        assert view.failure_reason == "Compte clos"
        assert uow.ledger.transactions == []
        payment = uow.merchant_payments.list_for_merchant(MERCHANT_ID)[0]
        assert payment.settlement_id is None
        assert payment.status is MerchantPaymentStatus.COMPLETED
        assert "MerchantSettlementFailed" in events.names()

    def test_non_merchant_rejected(self, services: AppServices) -> None:
        with pytest.raises(NotAMerchant):
            SettleMerchantNow(services=services, bank=_Bank()).execute(
                SettleMerchantNowCommand(merchant_user_id=MERCHANT_USER_ID)
            )


class TestReadModels:
    def test_list_and_statement(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _merchant(uow)
        _payment(uow, n=1, amount=10_000, fee=100)
        _configure(services)
        SettleMerchantNow(services=services, bank=_Bank()).execute(
            SettleMerchantNowCommand(merchant_user_id=MERCHANT_USER_ID)
        )

        rows = ListMerchantSettlements(services=services).execute(
            ListMerchantSettlementsCommand(merchant_user_id=MERCHANT_USER_ID)
        )
        assert len(rows) == 1
        settlement_id = rows[0].settlement_id

        statement = GetSettlementStatement(services=services).execute(
            GetSettlementStatementCommand(
                merchant_user_id=MERCHANT_USER_ID, settlement_id=settlement_id
            )
        )
        assert statement.settlement.settlement_id == settlement_id
        assert len(statement.lines) == 1
        assert statement.lines[0].net_minor == 9_900
        assert statement.to_dict()["lines"][0]["gross_minor"] == 10_000

    def test_statement_unknown_id_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _merchant(uow)
        with pytest.raises(InvalidInput, match="introuvable"):
            GetSettlementStatement(services=services).execute(
                GetSettlementStatementCommand(
                    merchant_user_id=MERCHANT_USER_ID,
                    settlement_id=str(UUID(int=999)),
                )
            )

    def test_statement_malformed_id_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _merchant(uow)
        with pytest.raises(InvalidInput, match="introuvable"):
            GetSettlementStatement(services=services).execute(
                GetSettlementStatementCommand(
                    merchant_user_id=MERCHANT_USER_ID, settlement_id="not-a-uuid"
                )
            )

    def test_list_non_merchant_rejected(self, services: AppServices) -> None:
        with pytest.raises(NotAMerchant):
            ListMerchantSettlements(services=services).execute(
                ListMerchantSettlementsCommand(merchant_user_id=MERCHANT_USER_ID)
            )

    def test_statement_non_merchant_rejected(self, services: AppServices) -> None:
        with pytest.raises(NotAMerchant):
            GetSettlementStatement(services=services).execute(
                GetSettlementStatementCommand(
                    merchant_user_id=MERCHANT_USER_ID, settlement_id=str(UUID(int=1))
                )
            )


class TestSettleMerchantHelper:
    def test_skip_advances_schedule_without_ledger(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        merchant = _merchant(uow)
        _configure(services, frequency="DAILY")
        merchant = uow.merchants.get(MERCHANT_ID)
        assert merchant is not None
        before = merchant.next_settlement_at
        assert before is not None
        services.clock.advance(days=2)

        with services.uow() as u:
            m = u.merchants.get(MERCHANT_ID)
            assert m is not None
            result = settle_merchant(
                u, m, bank=_Bank(), ids=services.ids, clock=services.clock
            )
            assert result is None
            assert m.next_settlement_at is not None and m.next_settlement_at > before
