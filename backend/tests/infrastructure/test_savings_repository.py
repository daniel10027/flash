"""Intégration : ``SqlAlchemySavingsPlanRepository`` et la colonne ``wallets.saved_minor``."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session, sessionmaker

from flash.domain.identity.user import User
from flash.domain.savings.plan import SavingsFrequency, SavingsPlan
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


def test_savings_plan_roundtrip_and_wallet_saved_column(
    session_factory: sessionmaker[Session],
) -> None:
    clock = FixedClock(T0)
    user = _user("+2250700000401")
    wallet = Wallet.open(
        wallet_id=EntityId(str(uuid7())), user_id=user.id, currency=XOF, now=T0
    )
    wallet.credit(Money(100_000, XOF), T0)
    plan_id = EntityId(str(uuid7()))

    with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
        uow.users.add(user)
        uow.wallets.add(wallet)
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
        plan = SavingsPlan.open(
            plan_id=plan_id,
            wallet_id=EntityId(str(wallet.id)),
            user_id=user.id,
            currency=XOF,
            name="Voyage",
            now=T0,
            annual_rate_bps=365,
            frequency=SavingsFrequency.WEEKLY,
            contribution_minor=5_000,
            target_minor=500_000,
        )
        plan.deposit(Money(40_000, XOF), T0)
        uow.savings.add(plan)
        w = uow.wallets.get_for_update(EntityId(str(wallet.id)))
        w.move_to_savings(Money(40_000, XOF), T0)
        uow.wallets.save(w)
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
        w = uow.wallets.get(EntityId(str(wallet.id)))
        assert w is not None
        assert w.available == Money(60_000, XOF)
        assert w.saved == Money(40_000, XOF)
        assert w.balance == Money(100_000, XOF)

        plan = uow.savings.get(plan_id)
        assert plan is not None
        assert plan.balance == Money(40_000, XOF)
        assert plan.frequency is SavingsFrequency.WEEKLY
        assert plan.next_contribution_at == T0 + timedelta(days=7)
        assert plan.target_minor == 500_000

        [by_user] = uow.savings.list_for_user(user.id)
        assert by_user.id == plan_id
        assert [p.id for p in uow.savings.list_active()] == [plan_id]

    # Accrual persiste l'accumulateur ; la capitalisation touche solde + wallet.saved.
    with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
        plan = uow.savings.get_for_update(plan_id)
        plan.accrue(T0 + timedelta(days=100))
        capitalised = plan.capitalise(T0 + timedelta(days=100))
        assert capitalised.is_positive
        uow.savings.save(plan)
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
        plan = uow.savings.get(plan_id)
        assert plan is not None
        assert plan.balance.amount_minor > 40_000
        assert plan.last_accrual_at == T0 + timedelta(days=100)

        due = uow.savings.list_contributions_due(T0 + timedelta(days=10))
        assert [p.id for p in due] == [plan_id]

    # Clôture : la ligne reste (statut CLOSED) mais quitte les listes des jobs.
    with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
        plan = uow.savings.get_for_update(plan_id)
        plan.close(T0 + timedelta(days=101))
        uow.savings.save(plan)
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
        assert uow.savings.list_active() == []
        assert uow.savings.list_contributions_due(T0 + timedelta(days=200)) == []
        closed = uow.savings.get(plan_id)
        assert closed is not None and closed.status.value == "CLOSED"
