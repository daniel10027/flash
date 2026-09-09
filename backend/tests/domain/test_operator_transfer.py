"""Tests de l'agrégat ``OperatorTransfer`` (BE-064/065)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from flash.domain.operators.transfer import (
    OperatorTransfer,
    OperatorTransferDirection,
    OperatorTransferStatus,
)
from flash.domain.shared.errors import InvalidInput, OperatorTransferNotResolvable
from flash.domain.shared.identifiers import EntityId, Msisdn
from flash.domain.shared.money import XOF, Currency, Money

T0 = datetime(2026, 1, 1, tzinfo=UTC)
TID = EntityId(UUID(int=1))
UID = EntityId(UUID(int=2))
WID = EntityId(UUID(int=3))
TXN = EntityId(UUID(int=9))
MSISDN = Msisdn("+2250701020304")


def xof(n: int) -> Money:
    return Money(n, XOF)


def _start(direction: OperatorTransferDirection, *, amount: int = 50_000, fee: int = 750):
    return OperatorTransfer.start(
        transfer_id=TID,
        user_id=UID,
        wallet_id=WID,
        operator="ORANGE_CI",
        direction=direction,
        msisdn=MSISDN,
        amount=xof(amount),
        fee=xof(fee),
        reference="OPO-1",
        now=T0,
    )


class TestStart:
    def test_starts_pending_and_records_event(self) -> None:
        t = _start(OperatorTransferDirection.PAYOUT)
        assert t.is_pending and t.status is OperatorTransferStatus.PENDING
        assert t.debit_total == xof(50_750)
        assert t.credit_net == xof(49_250)
        assert [e.name for e in t.pull_events()] == ["OperatorTransferInitiated"]

    def test_rejects_currency_mismatch(self) -> None:
        with pytest.raises(InvalidInput, match="devises"):
            OperatorTransfer.start(
                transfer_id=TID,
                user_id=UID,
                wallet_id=WID,
                operator="X",
                direction=OperatorTransferDirection.PAYOUT,
                msisdn=MSISDN,
                amount=xof(10),
                fee=Money(1, Currency.of("EUR")),
                reference="R",
                now=T0,
            )

    @pytest.mark.parametrize("amount,fee", [(0, 0), (-1, 0)])
    def test_rejects_non_positive_amount(self, amount: int, fee: int) -> None:
        with pytest.raises(InvalidInput, match="strictement positif"):
            _start(OperatorTransferDirection.PAYOUT, amount=amount, fee=fee)

    def test_rejects_negative_fee(self) -> None:
        with pytest.raises(InvalidInput, match="frais"):
            _start(OperatorTransferDirection.PAYOUT, fee=-1)


class TestResolution:
    def test_mark_succeeded(self) -> None:
        t = _start(OperatorTransferDirection.PAYOUT)
        t.pull_events()
        t.mark_succeeded(external_ref="op_abc", ledger_transaction_id=TXN, now=T0)
        assert t.status is OperatorTransferStatus.SUCCEEDED
        assert t.external_ref == "op_abc" and t.ledger_transaction_id == TXN
        assert [e.name for e in t.pull_events()] == ["OperatorTransferSucceeded"]

    def test_mark_failed(self) -> None:
        t = _start(OperatorTransferDirection.COLLECT)
        t.pull_events()
        t.mark_failed(reason="TIMEOUT", now=T0)
        assert t.status is OperatorTransferStatus.FAILED
        assert t.failure_reason == "TIMEOUT"
        assert [e.name for e in t.pull_events()] == ["OperatorTransferFailed"]

    def test_cannot_resolve_twice(self) -> None:
        t = _start(OperatorTransferDirection.PAYOUT)
        t.mark_succeeded(external_ref=None, ledger_transaction_id=TXN, now=T0)
        with pytest.raises(OperatorTransferNotResolvable):
            t.mark_failed(reason="x", now=T0)
        with pytest.raises(OperatorTransferNotResolvable):
            t.mark_succeeded(external_ref=None, ledger_transaction_id=TXN, now=T0)

    def test_attach_external_ref(self) -> None:
        t = _start(OperatorTransferDirection.PAYOUT)
        t.attach_external_ref("op_xyz")
        assert t.external_ref == "op_xyz"

    def test_repr(self) -> None:
        assert "PAYOUT" in repr(_start(OperatorTransferDirection.PAYOUT))
