"""Intégration : ``SqlAlchemyVaultRepository`` et la colonne ``wallets.vaulted_minor``."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.orm import Session, sessionmaker

from flash.domain.identity.user import User
from flash.domain.shared.identifiers import CountryCode, EntityId, Msisdn
from flash.domain.shared.money import XOF, Money
from flash.domain.vault.vault import Vault
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


def test_vault_roundtrip_and_wallet_vaulted_column(
    session_factory: sessionmaker[Session],
) -> None:
    clock = FixedClock(T0)
    user = _user("+2250700000301")
    wallet = Wallet.open(
        wallet_id=EntityId(str(uuid7())), user_id=user.id, currency=XOF, now=T0
    )
    wallet.credit(Money(100_000, XOF), T0)

    vault_id = EntityId(str(uuid7()))
    pocket_a = EntityId(str(uuid7()))
    pocket_b = EntityId(str(uuid7()))

    with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
        uow.users.add(user)
        uow.wallets.add(wallet)
        uow.commit()

    # Ouvre deux poches, alimente la première, déplace le solde du wallet.
    with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
        vault = Vault.for_wallet(
            vault_id=vault_id,
            wallet_id=EntityId(str(wallet.id)),
            user_id=user.id,
            currency=XOF,
            now=T0,
        )
        vault.open_pocket(pocket_id=pocket_a, name="Vacances", now=T0, goal_minor=200_000)
        vault.open_pocket(
            pocket_id=pocket_b, name="Bloqué", now=T0, locked_until=T0 + timedelta(days=30)
        )
        vault.deposit(pocket_id=pocket_a, amount=Money(40_000, XOF), now=T0)
        uow.vaults.add(vault)

        w = uow.wallets.get_for_update(EntityId(str(wallet.id)))
        w.move_to_vault(Money(40_000, XOF), T0)
        uow.wallets.save(w)
        uow.commit()

    # Relecture : agrégat reconstruit, invariant total == wallet.vaulted.
    with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
        w = uow.wallets.get(EntityId(str(wallet.id)))
        assert w is not None
        assert w.available == Money(60_000, XOF)
        assert w.vaulted == Money(40_000, XOF)
        assert w.balance == Money(100_000, XOF)

        vault = uow.vaults.get_for_wallet(EntityId(str(wallet.id)))
        assert vault is not None
        assert vault.total == Money(40_000, XOF) == w.vaulted
        assert [p.name for p in vault.pockets] == ["Vacances", "Bloqué"]
        assert vault.pocket(pocket_b).is_locked(T0)

        by_user = uow.vaults.get_for_user(user.id)
        assert by_user is not None and by_user.id == vault_id

    # Ferme la poche vide : la ligne disparaît.
    with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
        vault = uow.vaults.get_for_wallet(EntityId(str(wallet.id)))
        assert vault is not None
        vault.close_pocket(pocket_id=pocket_b, now=T0)
        uow.vaults.save(vault)
        uow.commit()

    with SqlAlchemyUnitOfWork(session_factory, clock) as uow:
        vault = uow.vaults.get_for_wallet(EntityId(str(wallet.id)))
        assert vault is not None
        assert [str(p.id) for p in vault.pockets] == [str(pocket_a)]


def test_missing_vault_reads_as_none(session_factory: sessionmaker[Session]) -> None:
    with SqlAlchemyUnitOfWork(session_factory, FixedClock(T0)) as uow:
        assert uow.vaults.get_for_wallet(EntityId(str(uuid7()))) is None
