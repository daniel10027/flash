"""Tests du job de réconciliation des soldes (BE-045)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from flash.application.jobs.reconcile import ReconcileWalletBalances
from flash.application.services import AppServices
from flash.domain.ledger.chart import Direction
from flash.domain.ledger.transaction import LedgerTransaction, Posting, TransactionKind
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import XOF, Money
from flash.domain.wallet.wallet import Wallet
from tests.support.fakes import (
    FixedClock,
    InMemoryIdempotencyStore,
    RecordingEventPublisher,
    SeqIdGenerator,
)
from tests.support.repositories import InMemoryUnitOfWork

T0 = datetime(2026, 1, 1, tzinfo=UTC)
USER = EntityId(str(UUID(int=1)))
WALLET = EntityId(str(UUID(int=100)))
ACC_A = EntityId(str(UUID(int=200)))
ACC_B = EntityId(str(UUID(int=201)))


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


def _wallet(uow: InMemoryUnitOfWork, *, available: int, reserved: int = 0) -> Wallet:
    wallet = Wallet.open(wallet_id=WALLET, user_id=USER, currency=XOF, now=T0)
    if available or reserved:
        wallet.credit(Money(available + reserved, XOF), T0)
    if reserved:
        wallet.reserve(Money(reserved, XOF), T0)
    wallet.pull_events()
    uow.wallets.add(wallet)
    return wallet


def _ledger_credit(uow: InMemoryUnitOfWork, amount: int) -> None:
    txn = LedgerTransaction(
        id=EntityId(str(UUID(int=900))),
        kind=TransactionKind.CASH_IN,
        postings=(
            Posting(account_id=ACC_A, direction=Direction.DEBIT, amount=Money(amount, XOF)),
            Posting(
                account_id=ACC_B,
                direction=Direction.CREDIT,
                amount=Money(amount, XOF),
                wallet_id=WALLET,
            ),
        ),
        occurred_at=T0,
        reference="SEED-1",
        reason="seed",
    )
    uow.ledger.add(txn)


def test_no_discrepancy_when_projection_matches_ledger(
    services: AppServices, uow: InMemoryUnitOfWork
) -> None:
    _wallet(uow, available=30_000, reserved=10_000)  # projection = 40 000
    _ledger_credit(uow, 40_000)

    report = ReconcileWalletBalances(services=services).execute()
    assert report.checked == 1
    assert report.ok is True
    assert report.to_dict()["discrepancies"] == []


def test_detects_discrepancy(services: AppServices, uow: InMemoryUnitOfWork) -> None:
    _wallet(uow, available=40_000)  # projection = 40 000
    _ledger_credit(uow, 35_000)  # ledger = 35 000

    report = ReconcileWalletBalances(services=services).execute()
    assert report.ok is False
    [d] = report.discrepancies
    assert d.wallet_id == str(WALLET)
    assert d.projected_minor == 40_000
    assert d.ledger_minor == 35_000
    assert d.delta_minor == 5_000
    assert report.to_dict()["discrepancies"][0]["delta_minor"] == 5_000


def test_checks_every_wallet_across_pages(
    services: AppServices, uow: InMemoryUnitOfWork, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("flash.application.jobs.reconcile._PAGE", 1)  # force la pagination
    _wallet(uow, available=0)
    for i in range(2, 5):
        w = Wallet.open(
            wallet_id=EntityId(str(UUID(int=100 + i))),
            user_id=EntityId(str(UUID(int=i))),
            currency=XOF,
            now=T0,
        )
        w.pull_events()
        uow.wallets.add(w)
    report = ReconcileWalletBalances(services=services).execute()
    assert report.checked == 4 and report.ok is True
