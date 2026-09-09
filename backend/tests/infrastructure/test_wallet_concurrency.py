"""Course sur un portefeuille : le verrou pessimiste de la UoW empêche un solde négatif
(BE-043). Deux transferts simultanés qui, cumulés, dépasseraient le solde : un seul
passe, l'autre échoue en ``InsufficientFunds``.

Nécessite un PostgreSQL réel (``FLASH_TEST_DATABASE_URL``) — le verrou ``FOR UPDATE``
n'a de sens qu'avec de vraies transactions concurrentes, donc on branche directement
sur l'``Engine`` (pas la connexion enveloppée / annulée des autres tests d'intégration).
"""

from __future__ import annotations

import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

import pytest
from sqlalchemy import Engine, delete, text
from sqlalchemy.orm import Session, sessionmaker

from flash.application.services import AppServices
from flash.application.transfers.send_p2p import SendP2PTransfer, SendP2PTransferCommand
from flash.domain.identity.user import User
from flash.domain.limits.limits import KycPolicy, LimitPolicy
from flash.domain.pricing.pricing import PricingService
from flash.domain.shared.errors import InsufficientFunds
from flash.domain.shared.identifiers import CountryCode, EntityId, Msisdn
from flash.domain.shared.money import XOF, Money
from flash.domain.wallet.wallet import Wallet
from flash.infrastructure.db.models import (
    LedgerPostingModel,
    LedgerTransactionModel,
    OutboxModel,
    PhoneNumberModel,
    UserModel,
    WalletModel,
)
from flash.infrastructure.db.uow import SqlAlchemyUnitOfWork
from flash.infrastructure.events import NullEventPublisher
from flash.infrastructure.ids import Uuid7Generator, uuid7
from flash.infrastructure.limits import NullLimitCounter, build_limit_repository
from flash.infrastructure.pricing import build_pricing_repository
from tests.support.fakes import FixedClock, InMemoryIdempotencyStore

pytestmark = pytest.mark.integration

T0 = datetime(2026, 1, 1, tzinfo=UTC)
SENDER = "+2250700000091"
RECIPIENT = "+2250700000092"


def _new_user(msisdn: str) -> User:
    user = User.register(
        user_id=EntityId(str(uuid7())),
        country=CountryCode("CI"),
        msisdn=Msisdn(msisdn),
        pin_hash="hashed:1397",
        now=T0,
    )
    user.activate(T0)
    return user


@pytest.fixture
def raw_factory(db_engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=db_engine, expire_on_commit=False, future=True)


@pytest.fixture
def _cleanup(db_engine: Engine) -> Iterator[None]:
    yield
    with db_engine.begin() as conn:
        conn.execute(delete(OutboxModel))
        conn.execute(delete(LedgerPostingModel))
        conn.execute(delete(LedgerTransactionModel))
        conn.execute(delete(WalletModel))
        conn.execute(delete(PhoneNumberModel))
        conn.execute(delete(UserModel))


def _services(raw_factory: sessionmaker[Session]) -> AppServices:
    return AppServices(
        uow=lambda: SqlAlchemyUnitOfWork(raw_factory, FixedClock(T0)),
        clock=FixedClock(T0),
        ids=Uuid7Generator(),
        events=NullEventPublisher(),
        idempotency=InMemoryIdempotencyStore(),
    )


def _transfer(raw_factory: sessionmaker[Session], sender_id: str, amount: int, key: str) -> str:
    use_case = SendP2PTransfer(
        services=_services(raw_factory),
        pricing=PricingService(build_pricing_repository()),
        limits=LimitPolicy(build_limit_repository(), NullLimitCounter()),
        kyc=KycPolicy(),
    )
    try:
        use_case.execute(
            SendP2PTransferCommand(
                sender_user_id=sender_id,
                recipient_phone_number=RECIPIENT,
                amount_minor=amount,
                idempotency_key=key,
                country="CI",
            )
        )
    except InsufficientFunds:
        return "insufficient"
    return "ok"


@pytest.mark.usefixtures("_cleanup")
def test_two_concurrent_transfers_cannot_overdraw(raw_factory: sessionmaker[Session]) -> None:
    sender = _new_user(SENDER)
    recipient = _new_user(RECIPIENT)
    sender_wallet = Wallet.open(
        wallet_id=EntityId(str(uuid7())), user_id=sender.id, currency=XOF, now=T0
    )
    recipient_wallet = Wallet.open(
        wallet_id=EntityId(str(uuid7())), user_id=recipient.id, currency=XOF, now=T0
    )
    sender_wallet.credit(Money(10_000, XOF), T0)

    with SqlAlchemyUnitOfWork(raw_factory, FixedClock(T0)) as uow:
        uow.users.add(sender)
        uow.users.add(recipient)
        uow.wallets.add(sender_wallet)
        uow.wallets.add(recipient_wallet)
        uow.commit()

    # Deux transferts de 8 000 (+ frais) lancés en même temps : le cumul dépasse 10 000.
    barrier = threading.Barrier(2)
    sender_id = str(sender.id)

    def run(key: str) -> str:
        barrier.wait()
        return _transfer(raw_factory, sender_id, 8_000, key)

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = sorted(pool.map(run, ["race-key-a", "race-key-b"]))

    assert results == ["insufficient", "ok"]  # exactement un passe

    with raw_factory() as session:
        balance = session.execute(
            text("SELECT available_minor FROM wallets WHERE id = :wid"),
            {"wid": str(sender_wallet.id)},
        ).scalar_one()
    assert balance >= 0
    assert balance == 10_000 - (8_000 + 64)  # 0,8 % de 8 000 = 64
