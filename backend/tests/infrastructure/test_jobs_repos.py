"""Intégration : méthodes de dépôt ajoutées pour les jobs (BE-044/045)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session, sessionmaker

from flash.domain.identity.user import User
from flash.domain.ledger.chart import AccountType, Direction
from flash.domain.ledger.transaction import LedgerTransaction, Posting, TransactionKind
from flash.domain.merchants.charge import MerchantCharge
from flash.domain.merchants.merchant import Merchant
from flash.domain.payments.request import PaymentRequest
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


def test_wallet_balance_and_list_all(session_factory: sessionmaker[Session]) -> None:
    clock = FixedClock(T0)
    sender = _user("+2250700000201")
    recipient = _user("+2250700000202")
    sw = Wallet.open(wallet_id=EntityId(str(uuid7())), user_id=sender.id, currency=XOF, now=T0)
    rw = Wallet.open(wallet_id=EntityId(str(uuid7())), user_id=recipient.id, currency=XOF, now=T0)
    sw.credit(Money(100_000, XOF), T0)

    with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
        uow.users.add(sender)
        uow.users.add(recipient)
        uow.wallets.add(sw)
        uow.wallets.add(rw)
        s_acc = uow.ledger.ensure_account(
            account_type=AccountType.CLIENT_LIABILITY, currency=XOF, owner_ref=str(sender.id)
        )
        r_acc = uow.ledger.ensure_account(
            account_type=AccountType.CLIENT_LIABILITY, currency=XOF, owner_ref=str(recipient.id)
        )
        fee_acc = uow.ledger.ensure_account(account_type=AccountType.FLASH_FEE_INCOME, currency=XOF)
        # amorçage : crédit de 100 000 sur le wallet émetteur
        boot_bank = uow.ledger.ensure_account(
            account_type=AccountType.BANK_SETTLEMENT, currency=XOF
        )
        uow.ledger.add(
            LedgerTransaction(
                id=EntityId(str(uuid7())),
                kind=TransactionKind.CASH_IN,
                postings=(
                    Posting(
                        account_id=boot_bank,
                        direction=Direction.DEBIT,
                        amount=Money(100_000, XOF),
                    ),
                    Posting(
                        account_id=s_acc,
                        direction=Direction.CREDIT,
                        amount=Money(100_000, XOF),
                        wallet_id=sw.id,
                    ),
                ),
                occurred_at=T0,
                reference="BOOT-1",
                reason="amorçage",
            )
        )
        txn = LedgerTransaction.transfer(
            id=EntityId(str(uuid7())),
            occurred_at=T0,
            reference="TRX-JOB-1",
            sender_account_id=s_acc,
            sender_wallet_id=sw.id,
            recipient_account_id=r_acc,
            recipient_wallet_id=rw.id,
            fee_income_account_id=fee_acc,
            amount=Money(20_000, XOF),
            fee=Money(160, XOF),
        )
        uow.ledger.add(txn)
        sw.debit(Money(20_160, XOF), T0)
        rw.credit(Money(20_000, XOF), T0)
        uow.wallets.save(sw)
        uow.wallets.save(rw)
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
        assert uow.ledger.wallet_balance(sw.id) == 100_000 - 20_160
        assert uow.ledger.wallet_balance(rw.id) == 20_000
        all_wallets = uow.wallets.list_all(limit=100)
        assert {str(w.id) for w in all_wallets} == {str(sw.id), str(rw.id)}
        # pagination
        first = uow.wallets.list_all(limit=1)
        assert len(first) == 1
        rest = uow.wallets.list_all(limit=10, after=EntityId(str(first[0].id)))
        assert len(rest) == 1 and str(rest[0].id) != str(first[0].id)


def test_list_expired_helpers(session_factory: sessionmaker[Session]) -> None:
    clock = FixedClock(T0)
    requester = _user("+2250700000211")
    payer = _user("+2250700000212")
    owner = _user("+2250700000213")
    merchant = Merchant.enroll(
        merchant_id=EntityId(str(uuid7())),
        user_id=owner.id,
        display_name="M",
        category="X",
        currency=XOF,
        fee_bps=100,
        now=T0,
    )
    fresh = PaymentRequest.open(
        request_id=EntityId(str(uuid7())),
        requester_id=requester.id,
        payer_id=payer.id,
        amount=Money(1_000, XOF),
        now=T0,
        expires_at=T0 + timedelta(days=7),
    )
    stale = PaymentRequest.open(
        request_id=EntityId(str(uuid7())),
        requester_id=requester.id,
        payer_id=payer.id,
        amount=Money(2_000, XOF),
        now=T0 - timedelta(days=10),
        expires_at=T0 - timedelta(days=1),
    )
    stale_charge = MerchantCharge.open(
        charge_id=EntityId(str(uuid7())),
        merchant_id=merchant.id,
        amount=Money(3_000, XOF),
        reference="R",
        now=T0 - timedelta(hours=2),
        expires_at=T0 - timedelta(minutes=1),
    )

    with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
        uow.users.add(requester)
        uow.users.add(payer)
        uow.users.add(owner)
        uow.commit()
    with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
        uow.merchants.add(merchant)
        uow.commit()
    with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
        uow.payment_requests.add(fresh)
        uow.payment_requests.add(stale)
        uow.merchant_charges.add(stale_charge)
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
        expired_reqs = uow.payment_requests.list_expired(T0)
        assert [str(r.id) for r in expired_reqs] == [str(stale.id)]
        expired_charges = uow.merchant_charges.list_expired(T0)
        assert [str(c.id) for c in expired_charges] == [str(stale_charge.id)]
        assert uow.cash_orders.list_expired_withdrawals(T0) == []
