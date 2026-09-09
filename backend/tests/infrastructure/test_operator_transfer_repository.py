"""Intégration : ``SqlAlchemyOperatorTransferRepository`` (BE-064/067)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy.orm import Session, sessionmaker

from flash.domain.identity.user import User
from flash.domain.operators.transfer import (
    OperatorTransfer,
    OperatorTransferDirection,
    OperatorTransferStatus,
)
from flash.domain.shared.identifiers import CountryCode, EntityId, Msisdn
from flash.domain.shared.money import XOF, Money
from flash.domain.wallet.wallet import Wallet
from flash.infrastructure.db.uow import SqlAlchemyUnitOfWork
from flash.infrastructure.ids import uuid7
from tests.support.fakes import FixedClock

pytestmark = pytest.mark.integration

T0 = datetime(2026, 1, 1, tzinfo=UTC)


def _user(msisdn: str) -> User:
    user = User.register(
        user_id=EntityId(str(uuid7())),
        country=CountryCode("CI"),
        msisdn=Msisdn(msisdn),
        pin_hash="hashed:1397",
        now=T0,
    )
    user.activate(T0)
    return user


def test_operator_transfer_roundtrip_and_lock(session_factory: sessionmaker[Session]) -> None:
    clock = FixedClock(T0)
    user = _user("+2250700000601")
    wallet = Wallet.open(
        wallet_id=EntityId(str(uuid7())), user_id=user.id, currency=XOF, now=T0
    )
    wallet.credit(Money(100_000, XOF), T0)
    transfer_id = EntityId(str(uuid7()))

    with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
        uow.users.add(user)
        uow.wallets.add(wallet)
        transfer = OperatorTransfer.start(
            transfer_id=transfer_id,
            user_id=user.id,
            wallet_id=EntityId(str(wallet.id)),
            operator="ORANGE_CI",
            direction=OperatorTransferDirection.PAYOUT,
            msisdn=Msisdn("+2250712345678"),
            amount=Money(50_000, XOF),
            fee=Money(750, XOF),
            reference="OPO-int-1",
            now=T0,
        )
        transfer.attach_external_ref("op_ext_int")
        uow.operator_transfers.add(transfer)
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
        loaded = uow.operator_transfers.get_by_reference("OPO-int-1")
        assert loaded is not None
        assert loaded.direction is OperatorTransferDirection.PAYOUT
        assert loaded.external_ref == "op_ext_int"
        assert loaded.debit_total == Money(50_750, XOF)
        assert [t.id for t in uow.operator_transfers.list_for_user(user.id)] == [transfer_id]

    with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
        locked = uow.operator_transfers.get_for_update_by_reference("OPO-int-1")
        locked.mark_succeeded(
            external_ref="op_ext_int", ledger_transaction_id=EntityId(str(uuid7())), now=T0
        )
        uow.operator_transfers.save(locked)
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
        final = uow.operator_transfers.get(transfer_id)
        assert final is not None and final.status is OperatorTransferStatus.SUCCEEDED
        assert final.resolved_at is not None


def test_get_for_update_missing_raises_keyerror(session_factory: sessionmaker[Session]) -> None:
    with SqlAlchemyUnitOfWork(session_factory, FixedClock(T0)) as uow, pytest.raises(KeyError):
        uow.operator_transfers.get_for_update_by_reference("OPO-nope")
