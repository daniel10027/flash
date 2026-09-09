"""Job BE-073 : versement périodique des commissions agent dues."""

from __future__ import annotations

from uuid import UUID

import pytest

from flash.application.jobs.agent_commission import PayDueAgentCommissions
from flash.application.services import AppServices
from flash.domain.agent.agent import Agent
from flash.domain.identity.pin import Pin
from flash.domain.identity.user import User
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


def _agent(
    uow: InMemoryUnitOfWork, *, n: int, float_available: int, earned: int, paid: int = 0
) -> None:
    user = User.register(
        user_id=EntityId(str(UUID(int=n))),
        country=CI,
        msisdn=Msisdn(f"+22507000000{n:02d}"),
        pin_hash=FakePinHasher().hash(Pin("1397")),
        now=FixedClock().now(),
    )
    user.activate(FixedClock().now())
    user.pull_events()
    uow.users.add(user)
    wallet = Wallet.open(
        wallet_id=EntityId(str(UUID(int=500 + n))),
        user_id=user.id,
        currency=XOF,
        now=FixedClock().now(),
    )
    wallet.pull_events()
    uow.wallets.add(wallet)
    uow.agents.add(
        Agent(
            id=EntityId(str(UUID(int=100 + n))),
            user_id=user.id,
            currency=XOF,
            float_available=Money(float_available, XOF),
            float_cap=Money(10_000_000, XOF),
            commission_bps=100,
            created_at=FixedClock().now(),
            commission_earned=Money(earned, XOF),
            commission_paid=Money(paid, XOF),
        )
    )


class TestPayDueAgentCommissions:
    def test_pays_agents_above_threshold(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _agent(uow, n=1, float_available=50_000, earned=5_000)
        _agent(uow, n=2, float_available=50_000, earned=200)  # sous le seuil

        report = PayDueAgentCommissions(services=services, threshold_minor=1_000).execute()
        assert report.checked == 1 and report.paid == 1
        assert report.paid_minor == 5_000 and report.skipped == 0

        again = PayDueAgentCommissions(services=services, threshold_minor=1_000).execute()
        assert again.checked == 0  # plus rien de dû

    def test_skips_agent_with_insufficient_float(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _agent(uow, n=1, float_available=100, earned=5_000)
        report = PayDueAgentCommissions(services=services, threshold_minor=1_000).execute()
        assert report.checked == 1 and report.paid == 0 and report.skipped == 1
        assert report.to_dict()["skipped"] == 1

    def test_no_candidates_is_noop(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _agent(uow, n=1, float_available=50_000, earned=100)
        report = PayDueAgentCommissions(services=services).execute()
        assert report.to_dict() == {"checked": 0, "paid": 0, "paid_minor": 0, "skipped": 0}
