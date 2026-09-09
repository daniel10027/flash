"""Dépôts concrets SQLAlchemy.

Chaque dépôt convertit entre modèles ORM et agrégats de domaine (via ``mappers``) et
enregistre les agrégats chargés/écrits auprès de la Unit of Work pour la collecte des
événements.
"""

from __future__ import annotations

from datetime import datetime
from typing import Protocol

from sqlalchemy import case, func, select
from sqlalchemy.orm import Session

from flash.domain.agent.agent import Agent
from flash.domain.card.authorization import CardAuthorization
from flash.domain.card.card import Card
from flash.domain.cash.order import CashOrder
from flash.domain.identity.kyc_case import KycCase
from flash.domain.identity.user import User
from flash.domain.ledger.chart import AccountType
from flash.domain.ledger.transaction import LedgerTransaction
from flash.domain.merchants.api_key import MerchantApiKey
from flash.domain.merchants.charge import MerchantCharge
from flash.domain.merchants.merchant import Merchant
from flash.domain.merchants.payment import MerchantPayment
from flash.domain.merchants.settlement import MerchantSettlement
from flash.domain.merchants.webhook import MerchantWebhookDelivery
from flash.domain.operators.transfer import OperatorTransfer
from flash.domain.payments.request import PaymentRequest
from flash.domain.savings.plan import SavingsPlan
from flash.domain.shared.errors import PhoneNumberAlreadyLinked
from flash.domain.shared.events import EventRecorder
from flash.domain.shared.identifiers import EntityId, Msisdn
from flash.domain.shared.money import Currency, Money
from flash.domain.support.ticket import SupportNote, SupportTicket
from flash.domain.vault.vault import Vault
from flash.domain.wallet.wallet import Wallet
from flash.infrastructure.db import mappers
from flash.infrastructure.db.models import (
    AgentModel,
    CardAuthorizationModel,
    CardModel,
    CashOrderModel,
    KycCaseModel,
    LedgerAccountModel,
    LedgerPostingModel,
    LedgerTransactionModel,
    MerchantApiKeyModel,
    MerchantChargeModel,
    MerchantModel,
    MerchantPaymentModel,
    MerchantSettlementModel,
    MerchantWebhookDeliveryModel,
    OperatorTransferModel,
    PaymentRequestModel,
    PhoneNumberModel,
    SavingsPlanModel,
    SupportNoteModel,
    SupportTicketModel,
    UserModel,
    VaultPocketModel,
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

    def list_all(self, *, limit: int = 1000, after: EntityId | None = None) -> list[Wallet]:
        stmt = select(WalletModel).order_by(WalletModel.id.asc()).limit(limit)
        if after is not None:
            stmt = stmt.where(WalletModel.id > str(after))
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

    def wallet_balance(self, wallet_id: EntityId) -> int:
        signed = case(
            (LedgerPostingModel.direction == "CREDIT", LedgerPostingModel.amount_minor),
            else_=-LedgerPostingModel.amount_minor,
        )
        stmt = select(func.coalesce(func.sum(signed), 0)).where(
            LedgerPostingModel.wallet_id == str(wallet_id)
        )
        return int(self._session.scalar(stmt) or 0)

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

    def list_with_commission_owed(self, threshold_minor: int) -> list[Agent]:
        stmt = select(AgentModel).where(
            AgentModel.status == "ACTIVE",
            (AgentModel.commission_earned_minor - AgentModel.commission_paid_minor)
            >= threshold_minor,
        )
        return [a for a in (self._load(m) for m in self._session.scalars(stmt)) if a is not None]

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

    def list_expired_withdrawals(self, now: datetime, *, limit: int = 500) -> list[CashOrder]:
        stmt = (
            select(CashOrderModel)
            .where(
                CashOrderModel.type == "WITHDRAWAL",
                CashOrderModel.status == "INITIATED",
                CashOrderModel.expires_at < now,
            )
            .order_by(CashOrderModel.expires_at.asc())
            .limit(limit)
            .with_for_update()
        )
        return [o for o in (self._load(m) for m in self._session.scalars(stmt)) if o is not None]

    def list_for_agent(self, agent_id: EntityId, *, limit: int = 50) -> list[CashOrder]:
        stmt = (
            select(CashOrderModel)
            .where(CashOrderModel.agent_id == str(agent_id))
            .order_by(CashOrderModel.created_at.desc())
            .limit(limit)
        )
        return [o for o in (self._load(m) for m in self._session.scalars(stmt)) if o is not None]

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

    def list_expired(self, now: datetime, *, limit: int = 500) -> list[PaymentRequest]:
        stmt = (
            select(PaymentRequestModel)
            .where(
                PaymentRequestModel.status == "PENDING",
                PaymentRequestModel.expires_at < now,
            )
            .order_by(PaymentRequestModel.expires_at.asc())
            .limit(limit)
        )
        return [r for r in (self._load(m) for m in self._session.scalars(stmt)) if r is not None]

    def add(self, request: PaymentRequest) -> None:
        self._session.add(mappers.payment_request_to_model(request))
        self._tracker.track(request)

    def save(self, request: PaymentRequest) -> None:
        self._session.merge(mappers.payment_request_to_model(request))
        self._tracker.track(request)


class SqlAlchemyMerchantRepository:
    def __init__(self, session: Session, tracker: _AggregateTracker) -> None:
        self._session = session
        self._tracker = tracker

    def _load(self, model: MerchantModel | None) -> Merchant | None:
        if model is None:
            return None
        merchant = mappers.merchant_to_domain(model)
        self._tracker.track(merchant)
        return merchant

    def get(self, merchant_id: EntityId) -> Merchant | None:
        return self._load(self._session.get(MerchantModel, str(merchant_id)))

    def get_by_user_id(self, user_id: EntityId) -> Merchant | None:
        stmt = select(MerchantModel).where(MerchantModel.user_id == str(user_id))
        return self._load(self._session.scalars(stmt).first())

    def get_for_update(self, merchant_id: EntityId) -> Merchant:
        stmt = (
            select(MerchantModel).where(MerchantModel.id == str(merchant_id)).with_for_update()
        )
        model = self._session.scalars(stmt).first()
        if model is None:
            raise KeyError(merchant_id)
        loaded = self._load(model)
        assert loaded is not None
        return loaded

    def list_due_for_settlement(
        self, now: datetime, *, limit: int = 500
    ) -> list[Merchant]:
        stmt = (
            select(MerchantModel)
            .where(
                MerchantModel.status == "ACTIVE",
                MerchantModel.bank_iban.is_not(None),
                MerchantModel.next_settlement_at.is_not(None),
                MerchantModel.next_settlement_at <= now,
            )
            .order_by(MerchantModel.next_settlement_at.asc())
            .limit(limit)
            .with_for_update()
        )
        return [m for m in (self._load(x) for x in self._session.scalars(stmt)) if m is not None]

    def add(self, merchant: Merchant) -> None:
        self._session.add(mappers.merchant_to_model(merchant))
        self._tracker.track(merchant)

    def save(self, merchant: Merchant) -> None:
        self._session.merge(mappers.merchant_to_model(merchant))
        self._tracker.track(merchant)


class SqlAlchemyMerchantChargeRepository:
    def __init__(self, session: Session, tracker: _AggregateTracker) -> None:
        self._session = session
        self._tracker = tracker

    def _load(self, model: MerchantChargeModel | None) -> MerchantCharge | None:
        if model is None:
            return None
        charge = mappers.merchant_charge_to_domain(model)
        self._tracker.track(charge)
        return charge

    def get(self, charge_id: EntityId) -> MerchantCharge | None:
        return self._load(self._session.get(MerchantChargeModel, str(charge_id)))

    def get_for_update(self, charge_id: EntityId) -> MerchantCharge:
        stmt = (
            select(MerchantChargeModel)
            .where(MerchantChargeModel.id == str(charge_id))
            .with_for_update()
        )
        model = self._session.scalars(stmt).first()
        if model is None:
            raise KeyError(charge_id)
        loaded = self._load(model)
        assert loaded is not None
        return loaded

    def list_for_merchant(self, merchant_id: EntityId) -> list[MerchantCharge]:
        stmt = (
            select(MerchantChargeModel)
            .where(MerchantChargeModel.merchant_id == str(merchant_id))
            .order_by(MerchantChargeModel.created_at.desc())
        )
        return [c for c in (self._load(m) for m in self._session.scalars(stmt)) if c is not None]

    def list_expired(self, now: datetime, *, limit: int = 500) -> list[MerchantCharge]:
        stmt = (
            select(MerchantChargeModel)
            .where(
                MerchantChargeModel.status == "PENDING",
                MerchantChargeModel.expires_at < now,
            )
            .order_by(MerchantChargeModel.expires_at.asc())
            .limit(limit)
        )
        return [c for c in (self._load(m) for m in self._session.scalars(stmt)) if c is not None]

    def add(self, charge: MerchantCharge) -> None:
        self._session.add(mappers.merchant_charge_to_model(charge))
        self._tracker.track(charge)

    def save(self, charge: MerchantCharge) -> None:
        self._session.merge(mappers.merchant_charge_to_model(charge))
        self._tracker.track(charge)


class SqlAlchemyMerchantPaymentRepository:
    def __init__(self, session: Session, tracker: _AggregateTracker) -> None:
        self._session = session
        self._tracker = tracker

    def _load(self, model: MerchantPaymentModel | None) -> MerchantPayment | None:
        if model is None:
            return None
        payment = mappers.merchant_payment_to_domain(model)
        self._tracker.track(payment)
        return payment

    def get(self, payment_id: EntityId) -> MerchantPayment | None:
        return self._load(self._session.get(MerchantPaymentModel, str(payment_id)))

    def get_by_ledger_transaction_id(self, txn_id: EntityId) -> MerchantPayment | None:
        stmt = select(MerchantPaymentModel).where(
            MerchantPaymentModel.ledger_transaction_id == str(txn_id)
        )
        return self._load(self._session.scalars(stmt).first())

    def list_for_merchant(self, merchant_id: EntityId) -> list[MerchantPayment]:
        stmt = (
            select(MerchantPaymentModel)
            .where(MerchantPaymentModel.merchant_id == str(merchant_id))
            .order_by(MerchantPaymentModel.created_at.desc())
        )
        return [p for p in (self._load(m) for m in self._session.scalars(stmt)) if p is not None]

    def list_settleable(self, merchant_id: EntityId) -> list[MerchantPayment]:
        stmt = (
            select(MerchantPaymentModel)
            .where(
                MerchantPaymentModel.merchant_id == str(merchant_id),
                MerchantPaymentModel.status == "COMPLETED",
                MerchantPaymentModel.settlement_id.is_(None),
            )
            .order_by(MerchantPaymentModel.created_at.asc())
            .with_for_update()
        )
        return [p for p in (self._load(m) for m in self._session.scalars(stmt)) if p is not None]

    def list_for_settlement(self, settlement_id: EntityId) -> list[MerchantPayment]:
        stmt = (
            select(MerchantPaymentModel)
            .where(MerchantPaymentModel.settlement_id == str(settlement_id))
            .order_by(MerchantPaymentModel.created_at.asc())
        )
        return [p for p in (self._load(m) for m in self._session.scalars(stmt)) if p is not None]

    def add(self, payment: MerchantPayment) -> None:
        self._session.add(mappers.merchant_payment_to_model(payment))
        self._tracker.track(payment)

    def save(self, payment: MerchantPayment) -> None:
        self._session.merge(mappers.merchant_payment_to_model(payment))
        self._tracker.track(payment)


class SqlAlchemyMerchantSettlementRepository:
    def __init__(self, session: Session, tracker: _AggregateTracker) -> None:
        self._session = session
        self._tracker = tracker

    def _load(self, model: MerchantSettlementModel | None) -> MerchantSettlement | None:
        if model is None:
            return None
        settlement = mappers.merchant_settlement_to_domain(model)
        self._tracker.track(settlement)
        return settlement

    def get(self, settlement_id: EntityId) -> MerchantSettlement | None:
        return self._load(self._session.get(MerchantSettlementModel, str(settlement_id)))

    def list_for_merchant(self, merchant_id: EntityId) -> list[MerchantSettlement]:
        stmt = (
            select(MerchantSettlementModel)
            .where(MerchantSettlementModel.merchant_id == str(merchant_id))
            .order_by(MerchantSettlementModel.created_at.desc())
        )
        return [s for s in (self._load(m) for m in self._session.scalars(stmt)) if s is not None]

    def add(self, settlement: MerchantSettlement) -> None:
        self._session.add(mappers.merchant_settlement_to_model(settlement))
        self._tracker.track(settlement)

    def save(self, settlement: MerchantSettlement) -> None:
        self._session.merge(mappers.merchant_settlement_to_model(settlement))
        self._tracker.track(settlement)


class SqlAlchemyMerchantApiKeyRepository:
    def __init__(self, session: Session, tracker: _AggregateTracker) -> None:
        self._session = session
        self._tracker = tracker

    def _load(self, model: MerchantApiKeyModel | None) -> MerchantApiKey | None:
        if model is None:
            return None
        api_key = mappers.merchant_api_key_to_domain(model)
        self._tracker.track(api_key)
        return api_key

    def get(self, key_id: EntityId) -> MerchantApiKey | None:
        return self._load(self._session.get(MerchantApiKeyModel, str(key_id)))

    def get_by_prefix(self, prefix: str) -> MerchantApiKey | None:
        stmt = select(MerchantApiKeyModel).where(MerchantApiKeyModel.prefix == prefix)
        return self._load(self._session.scalars(stmt).first())

    def list_for_merchant(self, merchant_id: EntityId) -> list[MerchantApiKey]:
        stmt = (
            select(MerchantApiKeyModel)
            .where(MerchantApiKeyModel.merchant_id == str(merchant_id))
            .order_by(MerchantApiKeyModel.created_at.desc())
        )
        return [k for k in (self._load(m) for m in self._session.scalars(stmt)) if k is not None]

    def add(self, api_key: MerchantApiKey) -> None:
        self._session.add(mappers.merchant_api_key_to_model(api_key))
        self._tracker.track(api_key)

    def save(self, api_key: MerchantApiKey) -> None:
        self._session.merge(mappers.merchant_api_key_to_model(api_key))
        self._tracker.track(api_key)


class SqlAlchemyMerchantWebhookDeliveryRepository:
    def __init__(self, session: Session, tracker: _AggregateTracker) -> None:
        self._session = session
        self._tracker = tracker

    def _load(
        self, model: MerchantWebhookDeliveryModel | None
    ) -> MerchantWebhookDelivery | None:
        if model is None:
            return None
        delivery = mappers.merchant_webhook_delivery_to_domain(model)
        self._tracker.track(delivery)
        return delivery

    def get(self, delivery_id: EntityId) -> MerchantWebhookDelivery | None:
        return self._load(
            self._session.get(MerchantWebhookDeliveryModel, str(delivery_id))
        )

    def exists_for_source(self, event_type: str, source_id: EntityId) -> bool:
        stmt = select(MerchantWebhookDeliveryModel.id).where(
            MerchantWebhookDeliveryModel.event_type == event_type,
            MerchantWebhookDeliveryModel.source_id == str(source_id),
        )
        return self._session.scalars(stmt).first() is not None

    def list_due(
        self, now: datetime, *, limit: int = 200
    ) -> list[MerchantWebhookDelivery]:
        stmt = (
            select(MerchantWebhookDeliveryModel)
            .where(
                MerchantWebhookDeliveryModel.status == "PENDING",
                MerchantWebhookDeliveryModel.next_attempt_at <= now,
            )
            .order_by(MerchantWebhookDeliveryModel.next_attempt_at)
            .limit(limit)
            .with_for_update(skip_locked=True)
        )
        return [
            d for d in (self._load(m) for m in self._session.scalars(stmt)) if d is not None
        ]

    def add(self, delivery: MerchantWebhookDelivery) -> None:
        self._session.add(mappers.merchant_webhook_delivery_to_model(delivery))
        self._tracker.track(delivery)

    def save(self, delivery: MerchantWebhookDelivery) -> None:
        self._session.merge(mappers.merchant_webhook_delivery_to_model(delivery))
        self._tracker.track(delivery)


class SqlAlchemyVaultRepository:
    """Le coffre est l'ensemble des lignes ``vault_pockets`` d'un portefeuille."""

    def __init__(self, session: Session, tracker: _AggregateTracker) -> None:
        self._session = session
        self._tracker = tracker

    def _load(self, models: list[VaultPocketModel]) -> Vault | None:
        vault = mappers.vault_to_domain(models)
        if vault is not None:
            self._tracker.track(vault)
        return vault

    def get_for_wallet(self, wallet_id: EntityId) -> Vault | None:
        stmt = (
            select(VaultPocketModel)
            .where(VaultPocketModel.wallet_id == str(wallet_id))
            .with_for_update()
        )
        return self._load(list(self._session.scalars(stmt)))

    def get_for_user(self, user_id: EntityId) -> Vault | None:
        stmt = (
            select(VaultPocketModel)
            .where(VaultPocketModel.user_id == str(user_id))
            .with_for_update()
        )
        return self._load(list(self._session.scalars(stmt)))

    def add(self, vault: Vault) -> None:
        for model in mappers.vault_pockets_to_models(vault):
            self._session.add(model)
        self._tracker.track(vault)

    def save(self, vault: Vault) -> None:
        wanted = {str(p.id) for p in vault.pockets}
        existing = self._session.scalars(
            select(VaultPocketModel).where(VaultPocketModel.vault_id == str(vault.id))
        )
        for model in existing:
            if model.id not in wanted:
                self._session.delete(model)
        for model in mappers.vault_pockets_to_models(vault):
            self._session.merge(model)
        self._tracker.track(vault)


class SqlAlchemySavingsPlanRepository:
    def __init__(self, session: Session, tracker: _AggregateTracker) -> None:
        self._session = session
        self._tracker = tracker

    def _load(self, model: SavingsPlanModel | None) -> SavingsPlan | None:
        if model is None:
            return None
        plan = mappers.savings_plan_to_domain(model)
        self._tracker.track(plan)
        return plan

    def get(self, plan_id: EntityId) -> SavingsPlan | None:
        return self._load(self._session.get(SavingsPlanModel, str(plan_id)))

    def get_for_update(self, plan_id: EntityId) -> SavingsPlan:
        stmt = (
            select(SavingsPlanModel).where(SavingsPlanModel.id == str(plan_id)).with_for_update()
        )
        model = self._session.scalars(stmt).first()
        if model is None:
            raise KeyError(plan_id)
        loaded = self._load(model)
        assert loaded is not None
        return loaded

    def list_for_user(self, user_id: EntityId) -> list[SavingsPlan]:
        stmt = (
            select(SavingsPlanModel)
            .where(SavingsPlanModel.user_id == str(user_id))
            .order_by(SavingsPlanModel.created_at.desc())
        )
        return [p for p in (self._load(m) for m in self._session.scalars(stmt)) if p is not None]

    def list_active(
        self, *, limit: int = 500, after: EntityId | None = None
    ) -> list[SavingsPlan]:
        stmt = (
            select(SavingsPlanModel)
            .where(SavingsPlanModel.status == "ACTIVE")
            .order_by(SavingsPlanModel.id.asc())
            .limit(limit)
        )
        if after is not None:
            stmt = stmt.where(SavingsPlanModel.id > str(after))
        return [p for p in (self._load(m) for m in self._session.scalars(stmt)) if p is not None]

    def list_contributions_due(self, now: datetime, *, limit: int = 500) -> list[SavingsPlan]:
        stmt = (
            select(SavingsPlanModel)
            .where(
                SavingsPlanModel.status == "ACTIVE",
                SavingsPlanModel.frequency != "NONE",
                SavingsPlanModel.next_contribution_at.is_not(None),
                SavingsPlanModel.next_contribution_at <= now,
            )
            .order_by(SavingsPlanModel.next_contribution_at.asc())
            .limit(limit)
            .with_for_update()
        )
        return [p for p in (self._load(m) for m in self._session.scalars(stmt)) if p is not None]

    def add(self, plan: SavingsPlan) -> None:
        self._session.add(mappers.savings_plan_to_model(plan))
        self._tracker.track(plan)

    def save(self, plan: SavingsPlan) -> None:
        self._session.merge(mappers.savings_plan_to_model(plan))
        self._tracker.track(plan)


class SqlAlchemyCardRepository:
    def __init__(self, session: Session, tracker: _AggregateTracker) -> None:
        self._session = session
        self._tracker = tracker

    def _load(self, model: CardModel | None) -> Card | None:
        if model is None:
            return None
        card = mappers.card_to_domain(model)
        self._tracker.track(card)
        return card

    def get(self, card_id: EntityId) -> Card | None:
        return self._load(self._session.get(CardModel, str(card_id)))

    def get_for_update(self, card_id: EntityId) -> Card:
        stmt = select(CardModel).where(CardModel.id == str(card_id)).with_for_update()
        model = self._session.scalars(stmt).first()
        if model is None:
            raise KeyError(card_id)
        loaded = self._load(model)
        assert loaded is not None
        return loaded

    def get_by_pan_token(self, pan_token: str) -> Card | None:
        stmt = select(CardModel).where(CardModel.pan_token == pan_token)
        return self._load(self._session.scalars(stmt).first())

    def list_for_user(self, user_id: EntityId) -> list[Card]:
        stmt = (
            select(CardModel)
            .where(CardModel.user_id == str(user_id))
            .order_by(CardModel.created_at.desc())
        )
        return [c for c in (self._load(m) for m in self._session.scalars(stmt)) if c is not None]

    def add(self, card: Card) -> None:
        self._session.add(mappers.card_to_model(card))
        self._tracker.track(card)

    def save(self, card: Card) -> None:
        self._session.merge(mappers.card_to_model(card))
        self._tracker.track(card)


class SqlAlchemyCardAuthorizationRepository:
    _SPEND_STATES = ("AUTHORIZED", "CAPTURED")

    def __init__(self, session: Session, tracker: _AggregateTracker) -> None:
        self._session = session
        self._tracker = tracker

    def _load(self, model: CardAuthorizationModel | None) -> CardAuthorization | None:
        if model is None:
            return None
        auth = mappers.card_authorization_to_domain(model)
        self._tracker.track(auth)
        return auth

    def get(self, auth_id: EntityId) -> CardAuthorization | None:
        return self._load(self._session.get(CardAuthorizationModel, str(auth_id)))

    def get_by_authorization_id(self, authorization_id: str) -> CardAuthorization | None:
        stmt = select(CardAuthorizationModel).where(
            CardAuthorizationModel.authorization_id == authorization_id
        )
        return self._load(self._session.scalars(stmt).first())

    def get_for_update_by_authorization_id(self, authorization_id: str) -> CardAuthorization:
        stmt = (
            select(CardAuthorizationModel)
            .where(CardAuthorizationModel.authorization_id == authorization_id)
            .with_for_update()
        )
        model = self._session.scalars(stmt).first()
        if model is None:
            raise KeyError(authorization_id)
        loaded = self._load(model)
        assert loaded is not None
        return loaded

    def total_spent_since(self, card_id: EntityId, since: datetime) -> Money:
        stmt = select(func.coalesce(func.sum(CardAuthorizationModel.amount_minor), 0)).where(
            CardAuthorizationModel.card_id == str(card_id),
            CardAuthorizationModel.created_at >= since,
            CardAuthorizationModel.status.in_(self._SPEND_STATES),
        )
        currency_stmt = select(CardModel.currency).where(CardModel.id == str(card_id))
        code = self._session.scalar(currency_stmt) or "XOF"
        return Money(int(self._session.scalar(stmt) or 0), Currency.of(code))

    def list_for_card(self, card_id: EntityId) -> list[CardAuthorization]:
        stmt = (
            select(CardAuthorizationModel)
            .where(CardAuthorizationModel.card_id == str(card_id))
            .order_by(CardAuthorizationModel.created_at.desc())
        )
        return [a for a in (self._load(m) for m in self._session.scalars(stmt)) if a is not None]

    def list_resolved(
        self, *, limit: int = 500, after: EntityId | None = None
    ) -> list[CardAuthorization]:
        stmt = (
            select(CardAuthorizationModel)
            .where(CardAuthorizationModel.status.in_(("CAPTURED", "REFUNDED")))
            .order_by(CardAuthorizationModel.id.asc())
            .limit(limit)
        )
        if after is not None:
            stmt = stmt.where(CardAuthorizationModel.id > str(after))
        return [a for a in (self._load(m) for m in self._session.scalars(stmt)) if a is not None]

    def add(self, authorization: CardAuthorization) -> None:
        self._session.add(mappers.card_authorization_to_model(authorization))
        self._tracker.track(authorization)

    def save(self, authorization: CardAuthorization) -> None:
        self._session.merge(mappers.card_authorization_to_model(authorization))
        self._tracker.track(authorization)


class SqlAlchemyOperatorTransferRepository:
    def __init__(self, session: Session, tracker: _AggregateTracker) -> None:
        self._session = session
        self._tracker = tracker

    def _load(self, model: OperatorTransferModel | None) -> OperatorTransfer | None:
        if model is None:
            return None
        transfer = mappers.operator_transfer_to_domain(model)
        self._tracker.track(transfer)
        return transfer

    def get(self, transfer_id: EntityId) -> OperatorTransfer | None:
        return self._load(self._session.get(OperatorTransferModel, str(transfer_id)))

    def get_by_reference(self, reference: str) -> OperatorTransfer | None:
        stmt = select(OperatorTransferModel).where(OperatorTransferModel.reference == reference)
        return self._load(self._session.scalars(stmt).first())

    def get_for_update_by_reference(self, reference: str) -> OperatorTransfer:
        stmt = (
            select(OperatorTransferModel)
            .where(OperatorTransferModel.reference == reference)
            .with_for_update()
        )
        model = self._session.scalars(stmt).first()
        if model is None:
            raise KeyError(reference)
        loaded = self._load(model)
        assert loaded is not None
        return loaded

    def list_for_user(self, user_id: EntityId) -> list[OperatorTransfer]:
        stmt = (
            select(OperatorTransferModel)
            .where(OperatorTransferModel.user_id == str(user_id))
            .order_by(OperatorTransferModel.created_at.desc())
        )
        return [t for t in (self._load(m) for m in self._session.scalars(stmt)) if t is not None]

    def add(self, transfer: OperatorTransfer) -> None:
        self._session.add(mappers.operator_transfer_to_model(transfer))
        self._tracker.track(transfer)

    def save(self, transfer: OperatorTransfer) -> None:
        self._session.merge(mappers.operator_transfer_to_model(transfer))
        self._tracker.track(transfer)


class SqlAlchemySupportNoteRepository:
    def __init__(self, session: Session, tracker: _AggregateTracker) -> None:
        self._session = session
        self._tracker = tracker

    def list_for_user(self, user_id: EntityId, *, limit: int = 100) -> list[SupportNote]:
        stmt = (
            select(SupportNoteModel)
            .where(SupportNoteModel.subject_user_id == str(user_id))
            .order_by(SupportNoteModel.created_at.desc())
            .limit(limit)
        )
        return [mappers.support_note_to_domain(m) for m in self._session.scalars(stmt)]

    def add(self, note: SupportNote) -> None:
        self._session.add(mappers.support_note_to_model(note))


class SqlAlchemySupportTicketRepository:
    def __init__(self, session: Session, tracker: _AggregateTracker) -> None:
        self._session = session
        self._tracker = tracker

    def get(self, ticket_id: EntityId) -> SupportTicket | None:
        model = self._session.get(SupportTicketModel, str(ticket_id))
        return mappers.support_ticket_to_domain(model) if model is not None else None

    def list_recent(
        self, *, status: str | None = None, limit: int = 100
    ) -> list[SupportTicket]:
        stmt = select(SupportTicketModel).order_by(SupportTicketModel.updated_at.desc())
        if status is not None:
            stmt = stmt.where(SupportTicketModel.status == status)
        stmt = stmt.limit(limit)
        return [mappers.support_ticket_to_domain(m) for m in self._session.scalars(stmt)]

    def list_for_user(
        self, user_id: EntityId, *, limit: int = 100
    ) -> list[SupportTicket]:
        stmt = (
            select(SupportTicketModel)
            .where(SupportTicketModel.subject_user_id == str(user_id))
            .order_by(SupportTicketModel.updated_at.desc())
            .limit(limit)
        )
        return [mappers.support_ticket_to_domain(m) for m in self._session.scalars(stmt)]

    def add(self, ticket: SupportTicket) -> None:
        self._session.add(mappers.support_ticket_to_model(ticket))

    def save(self, ticket: SupportTicket) -> None:
        self._session.merge(mappers.support_ticket_to_model(ticket))


def _new_account_id() -> EntityId:
    return EntityId(str(uuid7()))


__all__ = [
    "SqlAlchemyAgentRepository",
    "SqlAlchemyCardAuthorizationRepository",
    "SqlAlchemyCardRepository",
    "SqlAlchemyCashOrderRepository",
    "SqlAlchemyKycCaseRepository",
    "SqlAlchemyLedgerRepository",
    "SqlAlchemyMerchantApiKeyRepository",
    "SqlAlchemyMerchantChargeRepository",
    "SqlAlchemyMerchantPaymentRepository",
    "SqlAlchemyMerchantRepository",
    "SqlAlchemyMerchantSettlementRepository",
    "SqlAlchemyMerchantWebhookDeliveryRepository",
    "SqlAlchemyOperatorTransferRepository",
    "SqlAlchemyPaymentRequestRepository",
    "SqlAlchemySavingsPlanRepository",
    "SqlAlchemySupportNoteRepository",
    "SqlAlchemySupportTicketRepository",
    "SqlAlchemyUserRepository",
    "SqlAlchemyVaultRepository",
    "SqlAlchemyWalletRepository",
]
