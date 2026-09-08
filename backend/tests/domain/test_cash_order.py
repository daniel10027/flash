"""Tests de l'agrégat CashOrder (BE-034 → BE-036)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from flash.domain.cash.order import CashOrder, CashOrderStatus, CashOrderType
from flash.domain.shared.errors import (
    InvalidAccountState,
    WithdrawalCodeExpired,
    WithdrawalCodeInvalid,
)
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import XOF, Currency, Money

T0 = datetime(2026, 1, 1, tzinfo=UTC)
OID = EntityId(str(UUID(int=1)))
CLIENT = EntityId(str(UUID(int=2)))
AGENT = EntityId(str(UUID(int=3)))
TXN = EntityId(str(UUID(int=4)))


class TestDeposit:
    def test_deposit_is_immediately_confirmed(self) -> None:
        order = CashOrder.deposit(
            order_id=OID,
            client_id=CLIENT,
            agent_id=AGENT,
            amount=Money(40_000, XOF),
            ledger_transaction_id=TXN,
            now=T0,
        )
        assert order.type is CashOrderType.DEPOSIT
        assert order.status is CashOrderStatus.CONFIRMED
        assert order.fee == Money(0, XOF)
        assert order.total == Money(40_000, XOF)
        assert [e.name for e in order.pull_events()] == ["CashDepositCompleted"]

    def test_mixed_currency_rejected(self) -> None:
        with pytest.raises(ValueError, match="Devises"):
            CashOrder(
                id=OID,
                type=CashOrderType.DEPOSIT,
                client_id=CLIENT,
                amount=Money(1, XOF),
                fee=Money(1, Currency.of("EUR")),
                currency_code="XOF",
                status=CashOrderStatus.CONFIRMED,
                created_at=T0,
            )

    def test_non_positive_amount_rejected(self) -> None:
        with pytest.raises(ValueError, match="strictement positif"):
            CashOrder(
                id=OID,
                type=CashOrderType.DEPOSIT,
                client_id=CLIENT,
                amount=Money(0, XOF),
                fee=Money(0, XOF),
                currency_code="XOF",
                status=CashOrderStatus.CONFIRMED,
                created_at=T0,
            )

    def test_negative_fee_rejected(self) -> None:
        with pytest.raises(ValueError, match="négatifs"):
            CashOrder(
                id=OID,
                type=CashOrderType.WITHDRAWAL,
                client_id=CLIENT,
                amount=Money(1, XOF),
                fee=Money(-1, XOF),
                currency_code="XOF",
                status=CashOrderStatus.INITIATED,
                created_at=T0,
            )


def _withdrawal(*, expires_in: int = 15) -> CashOrder:
    return CashOrder.initiate_withdrawal(
        order_id=OID,
        client_id=CLIENT,
        amount=Money(30_000, XOF),
        fee=Money(0, XOF),
        code_hash="abc123",
        expires_at=T0 + timedelta(minutes=expires_in),
        now=T0,
    )


class TestWithdrawal:
    def test_initiate_is_pending(self) -> None:
        order = _withdrawal()
        assert order.type is CashOrderType.WITHDRAWAL
        assert order.status is CashOrderStatus.INITIATED
        assert [e.name for e in order.pull_events()] == ["CashWithdrawalInitiated"]

    def test_confirm_transitions_to_confirmed(self) -> None:
        order = _withdrawal()
        order.pull_events()
        order.confirm(agent_id=AGENT, code_matches=True, ledger_transaction_id=TXN, now=T0)
        assert order.status is CashOrderStatus.CONFIRMED
        assert order.agent_id == AGENT
        assert order.ledger_transaction_id == TXN
        assert [e.name for e in order.pull_events()] == ["CashWithdrawalConfirmed"]

    def test_confirm_wrong_code_rejected(self) -> None:
        with pytest.raises(WithdrawalCodeInvalid):
            _withdrawal().confirm(
                agent_id=AGENT, code_matches=False, ledger_transaction_id=TXN, now=T0
            )

    def test_confirm_expired_rejected(self) -> None:
        order = _withdrawal(expires_in=15)
        with pytest.raises(WithdrawalCodeExpired):
            order.confirm(
                agent_id=AGENT,
                code_matches=True,
                ledger_transaction_id=TXN,
                now=T0 + timedelta(minutes=20),
            )

    def test_confirm_non_initiated_rejected(self) -> None:
        order = _withdrawal()
        order.confirm(agent_id=AGENT, code_matches=True, ledger_transaction_id=TXN, now=T0)
        with pytest.raises(InvalidAccountState, match="plus en attente"):
            order.confirm(agent_id=AGENT, code_matches=True, ledger_transaction_id=TXN, now=T0)

    def test_confirm_deposit_rejected(self) -> None:
        deposit = CashOrder.deposit(
            order_id=OID,
            client_id=CLIENT,
            agent_id=AGENT,
            amount=Money(1, XOF),
            ledger_transaction_id=TXN,
            now=T0,
        )
        with pytest.raises(InvalidAccountState, match="Seul un retrait"):
            deposit.confirm(agent_id=AGENT, code_matches=True, ledger_transaction_id=TXN, now=T0)

    def test_cancel_transitions_and_is_final(self) -> None:
        order = _withdrawal()
        order.pull_events()
        order.cancel(T0)
        assert order.status is CashOrderStatus.CANCELLED
        assert [e.name for e in order.pull_events()] == ["CashWithdrawalCancelled"]
        with pytest.raises(InvalidAccountState):
            order.cancel(T0)

    def test_expire_only_from_initiated(self) -> None:
        order = _withdrawal()
        order.pull_events()
        order.expire(T0)
        assert order.status is CashOrderStatus.EXPIRED
        assert [e.name for e in order.pull_events()] == ["CashWithdrawalExpired"]
        order.expire(T0)  # no-op
        assert order.pull_events() == []
