"""Dépôts concrets SQLAlchemy.

Chaque dépôt convertit entre modèles ORM et agrégats de domaine (via ``mappers``) et
enregistre les agrégats chargés/écrits auprès de la Unit of Work pour la collecte des
événements.
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from flash.domain.identity.user import User
from flash.domain.ledger.chart import AccountType
from flash.domain.ledger.transaction import LedgerTransaction
from flash.domain.shared.errors import PhoneNumberAlreadyLinked
from flash.domain.shared.events import EventRecorder
from flash.domain.shared.identifiers import EntityId, Msisdn
from flash.domain.shared.money import Currency
from flash.domain.wallet.wallet import Wallet
from flash.infrastructure.db import mappers
from flash.infrastructure.db.models import (
    LedgerAccountModel,
    LedgerPostingModel,
    LedgerTransactionModel,
    PhoneNumberModel,
    UserModel,
    WalletModel,
)
from flash.infrastructure.ids import uuid7


class _AggregateTracker(Protocol):
    def track(self, aggregate: EventRecorder) -> None: ...


class SqlAlchemyUserRepository:
    def __init__(self, session: Session, tracker: _AggregateTracker) -> None:
        self._session = session
        self._tracker = tracker

    def get(self, user_id: EntityId) -> User | None:
        model = self._session.get(UserModel, str(user_id))
        if model is None:
            return None
        user = mappers.user_to_domain(model)
        self._tracker.track(user)
        return user

    def get_by_msisdn(self, msisdn: Msisdn) -> User | None:
        stmt = (
            select(UserModel)
            .join(PhoneNumberModel, PhoneNumberModel.user_id == UserModel.id)
            .where(PhoneNumberModel.msisdn == msisdn.value)
        )
        model = self._session.scalars(stmt).first()
        if model is None:
            return None
        user = mappers.user_to_domain(model)
        self._tracker.track(user)
        return user

    def exists_with_msisdn(self, msisdn: Msisdn) -> bool:
        stmt = select(PhoneNumberModel.id).where(PhoneNumberModel.msisdn == msisdn.value)
        return self._session.scalars(stmt).first() is not None

    def _guard_global_msisdn_uniqueness(self, user: User) -> None:
        values = [m.value for m in user.msisdns]
        stmt = select(PhoneNumberModel).where(PhoneNumberModel.msisdn.in_(values))
        for row in self._session.scalars(stmt):
            if row.user_id != str(user.id):
                raise PhoneNumberAlreadyLinked(msisdn=Msisdn(row.msisdn).masked())

    def add(self, user: User) -> None:
        self._guard_global_msisdn_uniqueness(user)
        self._session.add(mappers.user_to_model(user))
        self._tracker.track(user)

    def save(self, user: User) -> None:
        self._guard_global_msisdn_uniqueness(user)
        self._session.merge(mappers.user_to_model(user))
        self._tracker.track(user)


class SqlAlchemyWalletRepository:
    def __init__(self, session: Session, tracker: _AggregateTracker) -> None:
        self._session = session
        self._tracker = tracker

    def _load(self, model: WalletModel | None) -> Wallet | None:
        if model is None:
            return None
        wallet = mappers.wallet_to_domain(model)
        self._tracker.track(wallet)
        return wallet

    def get(self, wallet_id: EntityId) -> Wallet | None:
        return self._load(self._session.get(WalletModel, str(wallet_id)))

    def get_for_user(self, user_id: EntityId, currency: Currency) -> Wallet | None:
        stmt = select(WalletModel).where(
            WalletModel.user_id == str(user_id), WalletModel.currency == currency.code
        )
        return self._load(self._session.scalars(stmt).first())

    def list_for_user(self, user_id: EntityId) -> list[Wallet]:
        stmt = select(WalletModel).where(WalletModel.user_id == str(user_id))
        return [w for w in (self._load(m) for m in self._session.scalars(stmt)) if w is not None]

    def get_for_update(self, wallet_id: EntityId) -> Wallet:
        stmt = select(WalletModel).where(WalletModel.id == str(wallet_id)).with_for_update()
        model = self._session.scalars(stmt).first()
        if model is None:
            raise KeyError(wallet_id)
        loaded = self._load(model)
        assert loaded is not None
        return loaded

    def add(self, wallet: Wallet) -> None:
        self._session.add(mappers.wallet_to_model(wallet))
        self._tracker.track(wallet)

    def save(self, wallet: Wallet) -> None:
        self._session.merge(mappers.wallet_to_model(wallet))
        self._tracker.track(wallet)


class SqlAlchemyLedgerRepository:
    def __init__(self, session: Session) -> None:
        self._session = session

    def add(self, transaction: LedgerTransaction) -> None:
        self._session.add(mappers.ledger_transaction_to_model(transaction))

    def get(self, transaction_id: EntityId) -> LedgerTransaction | None:
        model = self._session.get(LedgerTransactionModel, str(transaction_id))
        return mappers.ledger_transaction_to_domain(model) if model is not None else None

    def get_by_reference(self, reference: str) -> list[LedgerTransaction]:
        stmt = select(LedgerTransactionModel).where(LedgerTransactionModel.reference == reference)
        return [mappers.ledger_transaction_to_domain(m) for m in self._session.scalars(stmt)]

    def list_for_wallet(
        self, wallet_id: EntityId, *, limit: int = 50, before: EntityId | None = None
    ) -> list[LedgerTransaction]:
        return self.list_for_wallets([wallet_id], limit=limit, before=before)

    def list_for_wallets(
        self, wallet_ids: list[EntityId], *, limit: int = 50, before: EntityId | None = None
    ) -> list[LedgerTransaction]:
        transaction_ids = select(LedgerPostingModel.transaction_id).where(
            LedgerPostingModel.wallet_id.in_([str(w) for w in wallet_ids])
        )
        stmt = select(LedgerTransactionModel).where(LedgerTransactionModel.id.in_(transaction_ids))
        if before is not None:
            # Les identifiants sont des UUIDv7 : l'ordre lexical suit l'ordre temporel.
            stmt = stmt.where(LedgerTransactionModel.id < str(before))
        stmt = stmt.order_by(LedgerTransactionModel.id.desc()).limit(limit)
        return [mappers.ledger_transaction_to_domain(m) for m in self._session.scalars(stmt)]

    def ensure_account(
        self,
        *,
        account_type: AccountType,
        currency: Currency,
        owner_ref: str | None = None,
    ) -> EntityId:
        stmt = select(LedgerAccountModel).where(
            LedgerAccountModel.type == account_type.value,
            LedgerAccountModel.currency == currency.code,
            LedgerAccountModel.owner_ref.is_(owner_ref)
            if owner_ref is None
            else LedgerAccountModel.owner_ref == owner_ref,
        )
        existing = self._session.scalars(stmt).first()
        if existing is not None:
            return EntityId(existing.id)
        new_id = _new_account_id()
        self._session.add(
            LedgerAccountModel(
                id=str(new_id),
                type=account_type.value,
                currency=currency.code,
                owner_ref=owner_ref,
            )
        )
        self._session.flush()
        return new_id


def _new_account_id() -> EntityId:
    return EntityId(str(uuid7()))


__all__ = [
    "SqlAlchemyLedgerRepository",
    "SqlAlchemyUserRepository",
    "SqlAlchemyWalletRepository",
]
