"""Tests de l'agrégat ``MerchantSettlement`` et des méthodes de règlement de ``Merchant``
(BE-070)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from flash.domain.merchants.bank_account import BankAccount
from flash.domain.merchants.merchant import Merchant, MerchantStatus, SettlementFrequency
from flash.domain.merchants.settlement import (
    MerchantSettlement,
    MerchantSettlementStatus,
)
from flash.domain.shared.errors import InvalidAccountState, InvalidInput
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import XOF, Money

T0 = datetime(2026, 1, 1, tzinfo=UTC)
SID = EntityId(str(UUID(int=10)))
MID = EntityId(str(UUID(int=1)))
UID = EntityId(str(UUID(int=2)))
TXN = EntityId(str(UUID(int=5)))


def _account() -> BankAccount:
    return BankAccount(
        holder="SARL Chez Awa",
        iban="CI93CI0080111301134291200589",
        bank_name="Ecobank CI",
    )


def _merchant() -> Merchant:
    return Merchant(
        id=MID,
        user_id=UID,
        display_name="Chez Awa",
        category="RESTAURANT",
        currency=XOF,
        fee_bps=100,
        created_at=T0,
        status=MerchantStatus.ACTIVE,
    )


class TestSettlementFrequency:
    @pytest.mark.parametrize(
        ("freq", "days"),
        [
            (SettlementFrequency.DAILY, 1),
            (SettlementFrequency.WEEKLY, 7),
            (SettlementFrequency.MONTHLY, 30),
        ],
    )
    def test_period(self, freq: SettlementFrequency, days: int) -> None:
        assert freq.period == timedelta(days=days)

    def test_manual_has_no_period(self) -> None:
        assert SettlementFrequency.MANUAL.period is None


class TestMerchantSettlementConfig:
    def test_configure_manual_leaves_no_schedule(self) -> None:
        merchant = _merchant()
        merchant.configure_settlement(
            bank_account=_account(), frequency=SettlementFrequency.MANUAL, now=T0
        )
        assert merchant.bank_account is not None
        assert merchant.next_settlement_at is None
        assert merchant.can_settle is True
        assert [e.name for e in merchant.pull_events()] == ["MerchantSettlementConfigured"]

    def test_configure_weekly_sets_next_schedule(self) -> None:
        merchant = _merchant()
        merchant.configure_settlement(
            bank_account=_account(), frequency=SettlementFrequency.WEEKLY, now=T0
        )
        assert merchant.next_settlement_at == T0 + timedelta(days=7)

    def test_require_bank_account_raises_when_unset(self) -> None:
        with pytest.raises(InvalidInput, match="bancaire"):
            _merchant().require_bank_account()

    def test_can_settle_false_when_suspended(self) -> None:
        merchant = _merchant()
        merchant.configure_settlement(
            bank_account=_account(), frequency=SettlementFrequency.WEEKLY, now=T0
        )
        merchant.suspend("fraude", T0)
        assert merchant.can_settle is False

    def test_due_for_settlement(self) -> None:
        merchant = _merchant()
        merchant.configure_settlement(
            bank_account=_account(), frequency=SettlementFrequency.DAILY, now=T0
        )
        assert merchant.due_for_settlement(T0 + timedelta(hours=23)) is False
        assert merchant.due_for_settlement(T0 + timedelta(days=1)) is True

    def test_due_for_settlement_false_without_bank_account(self) -> None:
        assert _merchant().due_for_settlement(T0 + timedelta(days=30)) is False

    def test_advance_schedule_catches_up_past_periods(self) -> None:
        merchant = _merchant()
        merchant.configure_settlement(
            bank_account=_account(), frequency=SettlementFrequency.DAILY, now=T0
        )
        merchant.advance_settlement_schedule(T0 + timedelta(days=3, hours=2))
        assert merchant.next_settlement_at == T0 + timedelta(days=4)

    def test_advance_schedule_noop_for_manual(self) -> None:
        merchant = _merchant()
        merchant.configure_settlement(
            bank_account=_account(), frequency=SettlementFrequency.MANUAL, now=T0
        )
        merchant.advance_settlement_schedule(T0 + timedelta(days=99))
        assert merchant.next_settlement_at is None

    def test_record_settlement_stores_id_and_advances(self) -> None:
        merchant = _merchant()
        merchant.configure_settlement(
            bank_account=_account(), frequency=SettlementFrequency.WEEKLY, now=T0
        )
        merchant.record_settlement(settlement_id=SID, now=T0 + timedelta(days=7))
        assert merchant.last_settlement_id == SID
        assert merchant.next_settlement_at == T0 + timedelta(days=14)


class TestMerchantSettlementAggregate:
    def test_open_records_event_and_is_pending(self) -> None:
        settlement = MerchantSettlement.open(
            settlement_id=SID,
            merchant_id=MID,
            user_id=UID,
            amount=Money(5_000, XOF),
            payment_count=3,
            now=T0,
        )
        assert settlement.is_pending
        assert settlement.currency_code == "XOF"
        assert [e.name for e in settlement.pull_events()] == ["MerchantSettlementOpened"]

    def test_open_rejects_non_positive_amount(self) -> None:
        with pytest.raises(InvalidInput, match="strictement positif"):
            MerchantSettlement.open(
                settlement_id=SID,
                merchant_id=MID,
                user_id=UID,
                amount=Money.zero(XOF),
                payment_count=1,
                now=T0,
            )

    def test_open_rejects_zero_payment_count(self) -> None:
        with pytest.raises(InvalidInput, match="au moins un paiement"):
            MerchantSettlement.open(
                settlement_id=SID,
                merchant_id=MID,
                user_id=UID,
                amount=Money(10, XOF),
                payment_count=0,
                now=T0,
            )

    def test_mark_paid_transitions_and_records_event(self) -> None:
        settlement = MerchantSettlement.open(
            settlement_id=SID,
            merchant_id=MID,
            user_id=UID,
            amount=Money(5_000, XOF),
            payment_count=2,
            now=T0,
        )
        settlement.pull_events()
        settlement.mark_paid(
            bank_reference="bank_abc123", ledger_transaction_id=TXN, now=T0
        )
        assert settlement.status is MerchantSettlementStatus.PAID
        assert settlement.bank_reference == "bank_abc123"
        assert settlement.ledger_transaction_id == TXN
        assert settlement.settled_at == T0
        assert [e.name for e in settlement.pull_events()] == ["MerchantSettlementPaid"]

    def test_mark_failed_transitions_and_records_event(self) -> None:
        settlement = MerchantSettlement.open(
            settlement_id=SID,
            merchant_id=MID,
            user_id=UID,
            amount=Money(5_000, XOF),
            payment_count=2,
            now=T0,
        )
        settlement.pull_events()
        settlement.mark_failed(reason="compte clos", now=T0)
        assert settlement.status is MerchantSettlementStatus.FAILED
        assert settlement.failure_reason == "compte clos"
        assert [e.name for e in settlement.pull_events()] == ["MerchantSettlementFailed"]

    def test_cannot_resolve_twice(self) -> None:
        settlement = MerchantSettlement.open(
            settlement_id=SID,
            merchant_id=MID,
            user_id=UID,
            amount=Money(5_000, XOF),
            payment_count=2,
            now=T0,
        )
        settlement.mark_paid(bank_reference="b", ledger_transaction_id=TXN, now=T0)
        with pytest.raises(InvalidAccountState, match="déjà résolu"):
            settlement.mark_failed(reason="trop tard", now=T0)

    def test_repr(self) -> None:
        settlement = MerchantSettlement.open(
            settlement_id=SID,
            merchant_id=MID,
            user_id=UID,
            amount=Money(5_000, XOF),
            payment_count=2,
            now=T0,
        )
        assert "MerchantSettlement(" in repr(settlement)
        assert "count=2" in repr(settlement)
