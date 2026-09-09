"""Tests du scan AML ``ScanForAmlAlerts`` (BE-076) : seuil CTR, structuration, vélocité."""

from __future__ import annotations

from datetime import timedelta
from uuid import UUID

import pytest

from flash.application.compliance.detection import AmlThresholds, ScanForAmlAlerts
from flash.application.services import AppServices
from flash.domain.identity.pin import Pin
from flash.domain.identity.user import User
from flash.domain.ledger.transaction import LedgerTransaction
from flash.domain.shared.identifiers import CountryCode, EntityId, Msisdn
from flash.domain.shared.money import XOF, Money
from flash.domain.wallet.wallet import Wallet
from tests.support.fakes import (
    FakePinHasher,
    FixedClock,
    InMemoryIdempotencyStore,
    RecordingEventPublisher,
    SeqIdGenerator,
)
from tests.support.repositories import InMemoryUnitOfWork

CI = CountryCode("CI")
USER_ID = EntityId(str(UUID(int=1)))
WALLET_ID = EntityId(str(UUID(int=501)))
PEER_ACC = EntityId(str(UUID(int=9001)))
FEE_ACC = EntityId(str(UUID(int=9002)))

THRESHOLDS = AmlThresholds(
    ctr_threshold_minor=1_000_000,
    lookback_hours=72,
    velocity_window_hours=24,
    velocity_max_count=4,
    velocity_max_volume_minor=3_000_000,
    structuring_window_hours=48,
    structuring_min_count=3,
)


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def services(uow: InMemoryUnitOfWork, clock: FixedClock) -> AppServices:
    return AppServices(
        uow=lambda: uow,
        clock=clock,
        ids=SeqIdGenerator(),
        events=RecordingEventPublisher(),
        idempotency=InMemoryIdempotencyStore(),
    )


def _user(uow: InMemoryUnitOfWork) -> None:
    user = User.register(
        user_id=USER_ID,
        country=CI,
        msisdn=Msisdn("+2250700000001"),
        pin_hash=FakePinHasher().hash(Pin("1397")),
        now=FixedClock().now(),
    )
    user.activate(FixedClock().now())
    user.pull_events()
    uow.users.add(user)
    wallet = Wallet.open(
        wallet_id=WALLET_ID, user_id=USER_ID, currency=XOF, now=FixedClock().now()
    )
    wallet.pull_events()
    uow.wallets.add(wallet)


def _debit(uow: InMemoryUnitOfWork, *, n: int, amount: int, at) -> None:
    """Une transaction où le portefeuille du client est débité de ``amount``."""
    uow.ledger.add(
        LedgerTransaction.transfer(
            id=EntityId(str(UUID(int=1000 + n))),
            occurred_at=at,
            reference=f"TRX-{n}",
            sender_account_id=EntityId(str(UUID(int=8000))),
            sender_wallet_id=WALLET_ID,
            recipient_account_id=PEER_ACC,
            recipient_wallet_id=EntityId(str(UUID(int=8888))),
            fee_income_account_id=FEE_ACC,
            amount=Money(amount, XOF),
            fee=Money(0, XOF),
        )
    )


class TestCtrThreshold:
    def test_single_large_debit_opens_ctr_alert(
        self, services: AppServices, uow: InMemoryUnitOfWork, clock: FixedClock
    ) -> None:
        _user(uow)
        _debit(uow, n=1, amount=1_500_000, at=clock.now())
        report = ScanForAmlAlerts(services=services, thresholds=THRESHOLDS).execute()
        assert report.alerts_opened == 1
        assert report.by_kind == {"CTR_THRESHOLD": 1}
        [alert] = uow.compliance_alerts.list_open()
        assert alert.kind.value == "CTR_THRESHOLD"
        assert alert.detail["amount_minor"] == 1_500_000

    def test_rerun_does_not_duplicate(
        self, services: AppServices, uow: InMemoryUnitOfWork, clock: FixedClock
    ) -> None:
        _user(uow)
        _debit(uow, n=1, amount=1_500_000, at=clock.now())
        ScanForAmlAlerts(services=services, thresholds=THRESHOLDS).execute()
        again = ScanForAmlAlerts(services=services, thresholds=THRESHOLDS).execute()
        assert again.alerts_opened == 0
        assert len(uow.compliance_alerts.list_open()) == 1


class TestStructuring:
    def test_multiple_near_threshold_debits_open_structuring(
        self, services: AppServices, uow: InMemoryUnitOfWork, clock: FixedClock
    ) -> None:
        _user(uow)
        for i in range(3):
            _debit(uow, n=i, amount=800_000, at=clock.now() - timedelta(hours=i))
        report = ScanForAmlAlerts(services=services, thresholds=THRESHOLDS).execute()
        kinds = {a.kind.value for a in uow.compliance_alerts.list_open()}
        assert "STRUCTURING" in kinds
        assert report.by_kind.get("STRUCTURING") == 1

    def test_too_few_near_debits_no_structuring(
        self, services: AppServices, uow: InMemoryUnitOfWork, clock: FixedClock
    ) -> None:
        _user(uow)
        for i in range(2):
            _debit(uow, n=i, amount=800_000, at=clock.now())
        ScanForAmlAlerts(services=services, thresholds=THRESHOLDS).execute()
        assert uow.compliance_alerts.list_open() == []


class TestVelocity:
    def test_many_debits_open_velocity(
        self, services: AppServices, uow: InMemoryUnitOfWork, clock: FixedClock
    ) -> None:
        _user(uow)
        for i in range(5):
            _debit(uow, n=i, amount=10_000, at=clock.now())
        ScanForAmlAlerts(services=services, thresholds=THRESHOLDS).execute()
        assert {a.kind.value for a in uow.compliance_alerts.list_open()} == {"VELOCITY"}

    def test_high_volume_opens_velocity(
        self, services: AppServices, uow: InMemoryUnitOfWork, clock: FixedClock
    ) -> None:
        _user(uow)
        _debit(uow, n=1, amount=900_000, at=clock.now())
        _debit(uow, n=2, amount=900_000, at=clock.now())
        _debit(uow, n=3, amount=900_000, at=clock.now())
        _debit(uow, n=4, amount=900_000, at=clock.now())
        report = ScanForAmlAlerts(services=services, thresholds=THRESHOLDS).execute()
        kinds = report.by_kind
        assert kinds.get("VELOCITY") == 1
        assert kinds.get("STRUCTURING") == 1


class TestNoise:
    def test_small_activity_no_alert(
        self, services: AppServices, uow: InMemoryUnitOfWork, clock: FixedClock
    ) -> None:
        _user(uow)
        _debit(uow, n=1, amount=5_000, at=clock.now())
        report = ScanForAmlAlerts(services=services, thresholds=THRESHOLDS).execute()
        assert report.alerts_opened == 0
        assert report.transactions_scanned == 1
        assert report.to_dict()["accounts_flagged"] == 0

    def test_old_transactions_ignored(
        self, services: AppServices, uow: InMemoryUnitOfWork, clock: FixedClock
    ) -> None:
        _user(uow)
        _debit(uow, n=1, amount=1_500_000, at=clock.now() - timedelta(hours=100))
        report = ScanForAmlAlerts(services=services, thresholds=THRESHOLDS).execute()
        assert report.transactions_scanned == 0
        assert report.alerts_opened == 0

    def test_credits_are_not_counted(
        self, services: AppServices, uow: InMemoryUnitOfWork, clock: FixedClock
    ) -> None:
        _user(uow)
        # le portefeuille du client est ici le *destinataire* (crédit), pas le débité
        uow.ledger.add(
            LedgerTransaction.transfer(
                id=EntityId(str(UUID(int=1))),
                occurred_at=clock.now(),
                reference="IN-1",
                sender_account_id=EntityId(str(UUID(int=7000))),
                sender_wallet_id=EntityId(str(UUID(int=7777))),
                recipient_account_id=EntityId(str(UUID(int=7001))),
                recipient_wallet_id=WALLET_ID,
                fee_income_account_id=FEE_ACC,
                amount=Money(2_000_000, XOF),
                fee=Money(0, XOF),
            )
        )
        report = ScanForAmlAlerts(services=services, thresholds=THRESHOLDS).execute()
        assert report.alerts_opened == 0
