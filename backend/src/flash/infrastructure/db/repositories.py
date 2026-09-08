"""Dépôts concrets SQLAlchemy.

Chaque dépôt convertit entre modèles ORM et agrégats de domaine (via ``mappers``) et
enregistre les agrégats chargés/écrits auprès de la Unit of Work pour la collecte des
événements.
"""

from __future__ import annotations

from typing import Protocol

from sqlalchemy import select
from sqlalchemy.orm import Session

from flash.domain.agent.agent import Agent
from flash.domain.cash.order import CashOrder
from flash.domain.identity.kyc_case import KycCase
from flash.domain.identity.user import User
from flash.domain.ledger.chart import AccountType
from flash.domain.ledger.transaction import LedgerTransaction
from flash.domain.payments.request import PaymentRequest
from flash.domain.shared.errors import PhoneNumberAlreadyLinked
from flash.domain.shared.events import EventRecorder
from flash.domain.shared.identifiers import EntityId, Msisdn
from flash.domain.shared.money import Currency
from flash.domain.wallet.wallet import Wallet
from flash.infrastructure.db import mappers
from flash.infrastructure.db.models import (
    AgentModel,
    CashOrderModel,
    KycCaseModel,
    LedgerAccountModel,
    LedgerPostingModel,
    LedgerTransactionModel,
    PaymentRequestModel,
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


class SqlAlchemyAgentRepository:
    def __init__(self, session: Session, tracker: _AggregateTracker) -> None:
        self._session = session
        self._tracker = tracker

    def _load(self, model: AgentModel | None) -> Agent | None:
        if model is None:
            return None
        agent = mappers.agent_to_domain(model)
        self._tracker.track(agent)
        return agent

    def get(self, agent_id: EntityId) -> Agent | None:
        return self._load(self._session.get(AgentModel, str(agent_id)))

    def get_by_user_id(self, user_id: EntityId) -> Agent | None:
        stmt = select(AgentModel).where(AgentModel.user_id == str(user_id))
        return self._load(self._session.scalars(stmt).first())

    def get_for_update(self, agent_id: EntityId) -> Agent:
        stmt = select(AgentModel).where(AgentModel.id == str(agent_id)).with_for_update()
        model = self._session.scalars(stmt).first()
        if model is None:
            raise KeyError(agent_id)
        loaded = self._load(model)
        assert loaded is not None
        return loaded

    def add(self, agent: Agent) -> None:
        self._session.add(mappers.agent_to_model(agent))
        self._tracker.track(agent)

    def save(self, agent: Agent) -> None:
        self._session.merge(mappers.agent_to_model(agent))
        self._tracker.track(agent)


class SqlAlchemyCashOrderRepository:
    def __init__(self, session: Session, tracker: _AggregateTracker) -> None:
        self._session = session
        self._tracker = tracker

    def _load(self, model: CashOrderModel | None) -> CashOrder | None:
        if model is None:
            return None
        order = mappers.cash_order_to_domain(model)
        self._tracker.track(order)
        return order

    def get(self, order_id: EntityId) -> CashOrder | None:
        return self._load(self._session.get(CashOrderModel, str(order_id)))

    def get_pending_withdrawal_by_code_hash(self, code_hash: str) -> CashOrder | None:
        stmt = (
            select(CashOrderModel)
            .where(
                CashOrderModel.code_hash == code_hash,
                CashOrderModel.status == "INITIATED",
            )
            .with_for_update()
        )
        return self._load(self._session.scalars(stmt).first())

    def add(self, order: CashOrder) -> None:
        self._session.add(mappers.cash_order_to_model(order))
        self._tracker.track(order)

    def save(self, order: CashOrder) -> None:
        self._session.merge(mappers.cash_order_to_model(order))
        self._tracker.track(order)


class SqlAlchemyKycCaseRepository:
    def __init__(self, session: Session, tracker: _AggregateTracker) -> None:
        self._session = session
        self._tracker = tracker

    def _load(self, model: KycCaseModel | None) -> KycCase | None:
        if model is None:
            return None
        case = mappers.kyc_case_to_domain(model)
        self._tracker.track(case)
        return case

    def get(self, case_id: EntityId) -> KycCase | None:
        return self._load(self._session.get(KycCaseModel, str(case_id)))

    def get_pending_for_user(self, user_id: EntityId) -> KycCase | None:
        stmt = (
            select(KycCaseModel)
            .where(KycCaseModel.user_id == str(user_id), KycCaseModel.status == "PENDING")
            .with_for_update()
        )
        return self._load(self._session.scalars(stmt).first())

    def list_for_user(self, user_id: EntityId) -> list[KycCase]:
        stmt = (
            select(KycCaseModel)
            .where(KycCaseModel.user_id == str(user_id))
            .order_by(KycCaseModel.submitted_at.desc())
        )
        return [c for c in (self._load(m) for m in self._session.scalars(stmt)) if c is not None]

    def add(self, case: KycCase) -> None:
        self._session.add(mappers.kyc_case_to_model(case))
        self._tracker.track(case)

    def save(self, case: KycCase) -> None:
        self._session.merge(mappers.kyc_case_to_model(case))
        self._tracker.track(case)


class SqlAlchemyPaymentRequestRepository:
    def __init__(self, session: Session, tracker: _AggregateTracker) -> None:
        self._session = session
        self._tracker = tracker

    def _load(self, model: PaymentRequestModel | None) -> PaymentRequest | None:
        if model is None:
            return None
        request = mappers.payment_request_to_domain(model)
        self._tracker.track(request)
        return request

    def get(self, request_id: EntityId) -> PaymentRequest | None:
        return self._load(self._session.get(PaymentRequestModel, str(request_id)))

    def list_incoming(self, payer_id: EntityId) -> list[PaymentRequest]:
        stmt = (
            select(PaymentRequestModel)
            .where(PaymentRequestModel.payer_id == str(payer_id))
            .order_by(PaymentRequestModel.created_at.desc())
        )
        return [r for r in (self._load(m) for m in self._session.scalars(stmt)) if r is not None]

    def list_outgoing(self, requester_id: EntityId) -> list[PaymentRequest]:
        stmt = (
            select(PaymentRequestModel)
            .where(PaymentRequestModel.requester_id == str(requester_id))
            .order_by(PaymentRequestModel.created_at.desc())
        )
        return [r for r in (self._load(m) for m in self._session.scalars(stmt)) if r is not None]

    def add(self, request: PaymentRequest) -> None:
        self._session.add(mappers.payment_request_to_model(request))
        self._tracker.track(request)

    def save(self, request: PaymentRequest) -> None:
        self._session.merge(mappers.payment_request_to_model(request))
        self._tracker.track(request)


def _new_account_id() -> EntityId:
    return EntityId(str(uuid7()))


__all__ = [
    "SqlAlchemyAgentRepository",
    "SqlAlchemyCashOrderRepository",
    "SqlAlchemyKycCaseRepository",
    "SqlAlchemyLedgerRepository",
    "SqlAlchemyPaymentRequestRepository",
    "SqlAlchemyUserRepository",
    "SqlAlchemyWalletRepository",
]
