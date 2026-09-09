"""Tests du ledger : chart, LedgerAccount, Posting, LedgerTransaction (BE-010, BE-011)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from flash.domain.ledger.account import LedgerAccount
from flash.domain.ledger.chart import AccountType, Direction, normal_balance
from flash.domain.ledger.transaction import (
    LedgerImbalance,
    LedgerTransaction,
    Posting,
    TransactionKind,
    sum_postings,
)
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import XOF, Money

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _id(n: int) -> EntityId:
    return EntityId(UUID(int=n))


def xof(n: int) -> Money:
    return Money(n, XOF)


# Comptes de référence pour les tests
SENDER = _id(101)
RECIPIENT = _id(102)
FEE_INCOME = _id(200)
AGENT_FLOAT = _id(300)
AGENT_COMMISSION = _id(301)
CLIENT = _id(103)
SAVINGS = _id(400)
INTEREST_EXPENSE = _id(401)
W_SENDER = _id(1101)
W_RECIPIENT = _id(1102)
W_CLIENT = _id(1103)


class TestChart:
    def test_direction_opposite(self) -> None:
        assert Direction.DEBIT.opposite is Direction.CREDIT
        assert Direction.CREDIT.opposite is Direction.DEBIT

    def test_normal_balances(self) -> None:
        assert normal_balance(AccountType.CLIENT_LIABILITY) is Direction.CREDIT
        assert normal_balance(AccountType.FLASH_FEE_INCOME) is Direction.CREDIT
        assert normal_balance(AccountType.AGENT_COMMISSION_EXPENSE) is Direction.DEBIT
        assert normal_balance(AccountType.BANK_SETTLEMENT) is Direction.DEBIT

    def test_every_account_type_has_a_normal_balance(self) -> None:
        for t in AccountType:
            assert normal_balance(t) in (Direction.DEBIT, Direction.CREDIT)


class TestLedgerAccount:
    def test_signed_amount_follows_normal_balance(self) -> None:
        liability = LedgerAccount(_id(1), AccountType.CLIENT_LIABILITY, XOF, owner_ref="u-1")
        # crédit sur un compte à solde créditeur => augmentation
        assert liability.signed_amount(Direction.CREDIT, xof(100)) == xof(100)
        assert liability.signed_amount(Direction.DEBIT, xof(100)) == xof(-100)

    def test_signed_amount_wrong_currency_rejected(self) -> None:
        from flash.domain.shared.money import Currency

        acct = LedgerAccount(_id(1), AccountType.FLASH_FEE_INCOME, XOF)
        with pytest.raises(ValueError):
            acct.signed_amount(Direction.CREDIT, Money(1, Currency.of("EUR")))


class TestPosting:
    def test_non_positive_amount_rejected(self) -> None:
        with pytest.raises(LedgerImbalance):
            Posting(account_id=_id(1), direction=Direction.DEBIT, amount=xof(0))

    def test_mirror_inverts_direction_only(self) -> None:
        p = Posting(account_id=_id(1), direction=Direction.DEBIT, amount=xof(50), wallet_id=_id(9))
        m = p.mirror()
        assert m.direction is Direction.CREDIT
        assert (m.account_id, m.amount, m.wallet_id) == (p.account_id, p.amount, p.wallet_id)


class TestBalanceInvariant:
    def test_unbalanced_transaction_rejected(self) -> None:
        with pytest.raises(LedgerImbalance, match="déséquilibrée"):
            LedgerTransaction(
                id=_id(1),
                kind=TransactionKind.ADJUSTMENT,
                postings=(
                    Posting(account_id=SENDER, direction=Direction.DEBIT, amount=xof(100)),
                    Posting(account_id=RECIPIENT, direction=Direction.CREDIT, amount=xof(90)),
                ),
                occurred_at=T0,
                reference="REF",
                reason="test",
            )

    def test_single_posting_rejected(self) -> None:
        with pytest.raises(LedgerImbalance, match="au moins deux"):
            LedgerTransaction(
                id=_id(1),
                kind=TransactionKind.ADJUSTMENT,
                postings=(Posting(account_id=SENDER, direction=Direction.DEBIT, amount=xof(100)),),
                occurred_at=T0,
                reference="REF",
                reason="test",
            )

    def test_metadata_is_frozen_after_construction(self) -> None:
        txn = LedgerTransaction.fee(
            id=_id(1),
            occurred_at=T0,
            reference="REF",
            source_account_id=SENDER,
            source_wallet_id=W_SENDER,
            fee_income_account_id=FEE_INCOME,
            fee=xof(80),
            metadata={"k": "v"},
        )
        assert txn.metadata["k"] == "v"
        with pytest.raises(TypeError):
            txn.metadata["k"] = "x"  # type: ignore[index]


class TestTransferFactory:
    def test_transfer_is_balanced_with_fee(self) -> None:
        txn = LedgerTransaction.transfer(
            id=_id(1),
            occurred_at=T0,
            reference="TRX-1",
            sender_account_id=SENDER,
            sender_wallet_id=W_SENDER,
            recipient_account_id=RECIPIENT,
            recipient_wallet_id=W_RECIPIENT,
            fee_income_account_id=FEE_INCOME,
            amount=xof(10_000),
            fee=xof(80),
        )
        assert txn.kind is TransactionKind.TRANSFER
        assert txn.is_balanced
        assert sum_postings(txn.postings) == {"XOF": 0}
        assert txn.total_amount() == xof(10_080)
        # 3 postings : débit émetteur 10 080, crédit destinataire 10 000, crédit frais 80
        debit = next(p for p in txn.postings if p.direction is Direction.DEBIT)
        assert debit.amount == xof(10_080)
        assert debit.wallet_id == W_SENDER

    def test_transfer_without_fee_has_two_postings(self) -> None:
        txn = LedgerTransaction.transfer(
            id=_id(1),
            occurred_at=T0,
            reference="TRX-2",
            sender_account_id=SENDER,
            sender_wallet_id=W_SENDER,
            recipient_account_id=RECIPIENT,
            recipient_wallet_id=W_RECIPIENT,
            fee_income_account_id=FEE_INCOME,
            amount=xof(5_000),
            fee=xof(0),
        )
        assert len(txn.postings) == 2
        assert txn.is_balanced


class TestCashFactories:
    def test_cash_in_balanced_with_commission(self) -> None:
        txn = LedgerTransaction.cash_in(
            id=_id(1),
            occurred_at=T0,
            reference="CI-1",
            agent_float_account_id=AGENT_FLOAT,
            client_account_id=CLIENT,
            client_wallet_id=W_CLIENT,
            amount=xof(20_000),
            commission=xof(150),
            agent_commission_expense_account_id=AGENT_COMMISSION,
        )
        assert txn.kind is TransactionKind.CASH_IN
        assert txn.is_balanced
        assert sum_postings(txn.postings) == {"XOF": 0}

    def test_cash_in_commission_without_expense_account_rejected(self) -> None:
        with pytest.raises(LedgerImbalance, match="commission"):
            LedgerTransaction.cash_in(
                id=_id(1),
                occurred_at=T0,
                reference="CI-2",
                agent_float_account_id=AGENT_FLOAT,
                client_account_id=CLIENT,
                client_wallet_id=W_CLIENT,
                amount=xof(20_000),
                commission=xof(150),
            )

    def test_cash_out_balanced_with_fee_and_commission(self) -> None:
        txn = LedgerTransaction.cash_out(
            id=_id(1),
            occurred_at=T0,
            reference="CO-1",
            client_account_id=CLIENT,
            client_wallet_id=W_CLIENT,
            agent_float_account_id=AGENT_FLOAT,
            fee_income_account_id=FEE_INCOME,
            amount=xof(15_000),
            fee=xof(120),
            commission=xof(90),
            agent_commission_expense_account_id=AGENT_COMMISSION,
        )
        assert txn.is_balanced
        debit = next(p for p in txn.postings if p.wallet_id == W_CLIENT)
        assert debit.amount == xof(15_120)

    def test_cash_out_without_fee_has_no_fee_posting(self) -> None:
        txn = LedgerTransaction.cash_out(
            id=_id(1),
            occurred_at=T0,
            reference="CO-3",
            client_account_id=CLIENT,
            client_wallet_id=W_CLIENT,
            agent_float_account_id=AGENT_FLOAT,
            fee_income_account_id=FEE_INCOME,
            amount=xof(15_000),
            fee=xof(0),
        )
        assert txn.is_balanced
        assert len(txn.postings) == 2

    def test_cash_out_zero_commission_ignored(self) -> None:
        txn = LedgerTransaction.cash_out(
            id=_id(1),
            occurred_at=T0,
            reference="CO-2",
            client_account_id=CLIENT,
            client_wallet_id=W_CLIENT,
            agent_float_account_id=AGENT_FLOAT,
            fee_income_account_id=FEE_INCOME,
            amount=xof(15_000),
            fee=xof(120),
            commission=xof(0),
        )
        assert txn.is_balanced
        assert len(txn.postings) == 3


class TestAgentFloatAndCommissionFactories:
    def test_float_topup_balanced(self) -> None:
        txn = LedgerTransaction.agent_float_topup(
            id=_id(1),
            occurred_at=T0,
            reference="AFT-1",
            bank_settlement_account_id=_id(700),
            agent_float_account_id=AGENT_FLOAT,
            amount=xof(500_000),
        )
        assert txn.kind is TransactionKind.AGENT_FLOAT_TOPUP
        assert txn.is_balanced and sum_postings(txn.postings) == {"XOF": 0}

    def test_float_withdraw_balanced_and_mirrors_topup(self) -> None:
        txn = LedgerTransaction.agent_float_withdraw(
            id=_id(2),
            occurred_at=T0,
            reference="AFW-1",
            agent_float_account_id=AGENT_FLOAT,
            bank_settlement_account_id=_id(700),
            amount=xof(200_000),
        )
        assert txn.kind is TransactionKind.AGENT_FLOAT_WITHDRAW
        assert txn.is_balanced and sum_postings(txn.postings) == {"XOF": 0}
        debit = next(p for p in txn.postings if p.direction is Direction.DEBIT)
        assert debit.account_id == AGENT_FLOAT

    def test_commission_payout_credits_agent_wallet(self) -> None:
        txn = LedgerTransaction.agent_commission_payout(
            id=_id(3),
            occurred_at=T0,
            reference="ACP-1",
            agent_float_account_id=AGENT_FLOAT,
            agent_wallet_account_id=CLIENT,
            agent_wallet_id=W_CLIENT,
            amount=xof(3_500),
        )
        assert txn.kind is TransactionKind.AGENT_COMMISSION_PAYOUT
        assert txn.is_balanced and sum_postings(txn.postings) == {"XOF": 0}
        credit = next(p for p in txn.postings if p.direction is Direction.CREDIT)
        assert credit.account_id == CLIENT and credit.wallet_id == W_CLIENT


class TestVaultSavingsInterest:
    def test_vault_move_into_and_out(self) -> None:
        into = LedgerTransaction.vault_move(
            id=_id(1),
            occurred_at=T0,
            reference="V-1",
            client_account_id=CLIENT,
            savings_account_id=SAVINGS,
            wallet_id=W_CLIENT,
            pocket_ref="pocket-42",
            amount=xof(5_000),
            into_vault=True,
        )
        assert into.kind is TransactionKind.VAULT_MOVE
        assert into.is_balanced
        debit = next(p for p in into.postings if p.direction is Direction.DEBIT)
        assert debit.account_id == CLIENT and debit.analytic == "pocket-42"

        out = LedgerTransaction.vault_move(
            id=_id(2),
            occurred_at=T0,
            reference="V-2",
            client_account_id=CLIENT,
            savings_account_id=SAVINGS,
            wallet_id=W_CLIENT,
            pocket_ref="pocket-42",
            amount=xof(5_000),
            into_vault=False,
        )
        debit_out = next(p for p in out.postings if p.direction is Direction.DEBIT)
        assert debit_out.account_id == SAVINGS

    def test_savings_deposit_and_withdrawal_balanced(self) -> None:
        dep = LedgerTransaction.savings_deposit(
            id=_id(1),
            occurred_at=T0,
            reference="S-1",
            client_account_id=CLIENT,
            savings_account_id=SAVINGS,
            wallet_id=W_CLIENT,
            plan_ref="plan-7",
            amount=xof(2_000),
        )
        wd = LedgerTransaction.savings_withdrawal(
            id=_id(2),
            occurred_at=T0,
            reference="S-2",
            client_account_id=CLIENT,
            savings_account_id=SAVINGS,
            wallet_id=W_CLIENT,
            plan_ref="plan-7",
            amount=xof(2_500),
        )
        assert dep.kind is TransactionKind.SAVINGS_DEPOSIT and dep.is_balanced
        assert wd.kind is TransactionKind.SAVINGS_WITHDRAWAL and wd.is_balanced

    def test_interest_capitalisation_balanced(self) -> None:
        txn = LedgerTransaction.interest(
            id=_id(1),
            occurred_at=T0,
            reference="INT-1",
            interest_expense_account_id=INTEREST_EXPENSE,
            savings_account_id=SAVINGS,
            wallet_id=W_CLIENT,
            plan_ref="plan-7",
            amount=xof(45),
        )
        assert txn.kind is TransactionKind.INTEREST
        assert txn.is_balanced
        credit = next(p for p in txn.postings if p.direction is Direction.CREDIT)
        assert credit.account_id == SAVINGS and credit.analytic == "plan-7"


class TestOperatorInterop:
    def test_payout_balanced_client_pays_amount_plus_fee(self) -> None:
        txn = LedgerTransaction.operator_payout(
            id=_id(1),
            occurred_at=T0,
            reference="OPO-1",
            client_account_id=CLIENT,
            client_wallet_id=W_CLIENT,
            operator_suspense_account_id=_id(500),
            fee_income_account_id=FEE_INCOME,
            amount=xof(50_000),
            fee=xof(750),
        )
        assert txn.kind is TransactionKind.OPERATOR_PAYOUT
        assert txn.is_balanced and sum_postings(txn.postings) == {"XOF": 0}
        debit = next(p for p in txn.postings if p.direction is Direction.DEBIT)
        assert debit.account_id == CLIENT and debit.amount == xof(50_750)

    def test_collect_balanced_client_gets_amount_minus_fee(self) -> None:
        txn = LedgerTransaction.operator_collect(
            id=_id(2),
            occurred_at=T0,
            reference="OPC-1",
            operator_suspense_account_id=_id(500),
            client_account_id=CLIENT,
            client_wallet_id=W_CLIENT,
            fee_income_account_id=FEE_INCOME,
            amount=xof(30_000),
            fee=xof(300),
        )
        assert txn.kind is TransactionKind.OPERATOR_COLLECT
        assert txn.is_balanced and sum_postings(txn.postings) == {"XOF": 0}
        credit = next(
            p for p in txn.postings if p.direction is Direction.CREDIT and p.wallet_id is not None
        )
        assert credit.account_id == CLIENT and credit.amount == xof(29_700)

    def test_zero_fee_variants_are_balanced(self) -> None:
        payout = LedgerTransaction.operator_payout(
            id=_id(3),
            occurred_at=T0,
            reference="OPO-2",
            client_account_id=CLIENT,
            client_wallet_id=W_CLIENT,
            operator_suspense_account_id=_id(500),
            fee_income_account_id=FEE_INCOME,
            amount=xof(1_000),
            fee=xof(0),
        )
        collect = LedgerTransaction.operator_collect(
            id=_id(4),
            occurred_at=T0,
            reference="OPC-2",
            operator_suspense_account_id=_id(500),
            client_account_id=CLIENT,
            client_wallet_id=W_CLIENT,
            fee_income_account_id=FEE_INCOME,
            amount=xof(1_000),
            fee=xof(0),
        )
        assert payout.is_balanced and len(payout.postings) == 2
        assert collect.is_balanced and len(collect.postings) == 2


class TestMerchantSettlementFactory:
    def test_balanced_payable_down_bank_down(self) -> None:
        txn = LedgerTransaction.merchant_settlement(
            id=_id(1),
            occurred_at=T0,
            reference="MSET-1",
            merchant_payable_account_id=_id(600),
            bank_settlement_account_id=_id(601),
            amount=xof(45_000),
            metadata={"merchant_name": "Chez Awa", "payment_count": 3},
        )
        assert txn.kind is TransactionKind.MERCHANT_SETTLEMENT
        assert txn.is_balanced and sum_postings(txn.postings) == {"XOF": 0}
        debit = next(p for p in txn.postings if p.direction is Direction.DEBIT)
        credit = next(p for p in txn.postings if p.direction is Direction.CREDIT)
        assert debit.account_id == _id(600) and debit.amount == xof(45_000)
        assert credit.account_id == _id(601) and credit.amount == xof(45_000)
        assert txn.metadata["payment_count"] == 3

    def test_metadata_defaults_to_empty(self) -> None:
        txn = LedgerTransaction.merchant_settlement(
            id=_id(2),
            occurred_at=T0,
            reference="MSET-2",
            merchant_payable_account_id=_id(600),
            bank_settlement_account_id=_id(601),
            amount=xof(1_000),
        )
        assert txn.metadata == {}
        assert len(txn.postings) == 2


class TestReversal:
    def _transfer(self) -> LedgerTransaction:
        return LedgerTransaction.transfer(
            id=_id(1),
            occurred_at=T0,
            reference="TRX-1",
            sender_account_id=SENDER,
            sender_wallet_id=W_SENDER,
            recipient_account_id=RECIPIENT,
            recipient_wallet_id=W_RECIPIENT,
            fee_income_account_id=FEE_INCOME,
            amount=xof(10_000),
            fee=xof(80),
        )

    def test_reversal_mirrors_every_posting(self) -> None:
        original = self._transfer()
        rev = LedgerTransaction.reversal(
            id=_id(2), original=original, occurred_at=T0, reason="erreur de saisie"
        )
        assert rev.kind is TransactionKind.REVERSAL
        assert rev.reverses_transaction_id == original.id
        assert rev.is_balanced
        for orig_p, rev_p in zip(original.postings, rev.postings, strict=True):
            assert rev_p.direction is orig_p.direction.opposite
            assert rev_p.amount == orig_p.amount
            assert rev_p.account_id == orig_p.account_id

    def test_cannot_reverse_a_reversal(self) -> None:
        rev = LedgerTransaction.reversal(
            id=_id(2), original=self._transfer(), occurred_at=T0, reason="x"
        )
        with pytest.raises(LedgerImbalance, match="contre-passation"):
            LedgerTransaction.reversal(id=_id(3), original=rev, occurred_at=T0, reason="y")


class TestTotalAmountGuard:
    def test_total_amount_rejects_multi_currency(self) -> None:
        from flash.domain.shared.money import Currency

        eur = Currency.of("EUR")
        txn = LedgerTransaction(
            id=_id(1),
            kind=TransactionKind.ADJUSTMENT,
            postings=(
                Posting(account_id=_id(10), direction=Direction.DEBIT, amount=xof(100)),
                Posting(account_id=_id(11), direction=Direction.CREDIT, amount=xof(100)),
                Posting(account_id=_id(12), direction=Direction.DEBIT, amount=Money(5, eur)),
                Posting(account_id=_id(13), direction=Direction.CREDIT, amount=Money(5, eur)),
            ),
            occurred_at=T0,
            reference="MIX",
            reason="multi-devise",
        )
        assert txn.is_balanced
        with pytest.raises(ValueError, match="mono-devise"):
            txn.total_amount()
