"""Dépôts et Unit of Work en mémoire pour les tests de la couche application.

Respectent les contrats des ports de ``flash.domain`` sans aucune I/O. Le suivi des
agrégats manipulés permet à ``InMemoryUnitOfWork.collect_new_events`` de récupérer les
événements après un cas d'usage.
"""

from __future__ import annotations

from collections.abc import Iterable

from flash.domain.agent.agent import Agent
from flash.domain.cash.order import CashOrder, CashOrderStatus, CashOrderType
from flash.domain.identity.kyc_case import KycCase, KycCaseStatus
from flash.domain.identity.user import User
from flash.domain.ledger.chart import AccountType
from flash.domain.ledger.transaction import LedgerTransaction
from flash.domain.merchants.charge import MerchantCharge
from flash.domain.merchants.merchant import Merchant
from flash.domain.merchants.payment import MerchantPayment
from flash.domain.payments.request import PaymentRequest
from flash.domain.shared.errors import PhoneNumberAlreadyLinked
from flash.domain.shared.events import DomainEvent, EventRecorder
from flash.domain.shared.identifiers import EntityId, Msisdn
from flash.domain.shared.money import Currency
from flash.domain.wallet.wallet import Wallet


class _Tracking:
    """Mémorise les agrégats touchés pour la collecte d'événements."""

    def __init__(self) -> None:
        self.seen: list[EventRecorder] = []

    def _track(self, aggregate: EventRecorder) -> None:
        if aggregate not in self.seen:
            self.seen.append(aggregate)


class InMemoryUserRepository(_Tracking):
    def __init__(self) -> None:
        super().__init__()
        self._by_id: dict[str, User] = {}

    def get(self, user_id: EntityId) -> User | None:
        user = self._by_id.get(str(user_id))
        if user is not None:
            self._track(user)
        return user

    def get_by_msisdn(self, msisdn: Msisdn) -> User | None:
        for user in self._by_id.values():
            if msisdn in user.msisdns:
                self._track(user)
                return user
        return None

    def exists_with_msisdn(self, msisdn: Msisdn) -> bool:
        return any(msisdn in u.msisdns for u in self._by_id.values())

    def _assert_msisdns_free(self, user: User) -> None:
        for other_id, other in self._by_id.items():
            if other_id == str(user.id):
                continue
            if user.msisdns & other.msisdns:
                raise PhoneNumberAlreadyLinked()

    def add(self, user: User) -> None:
        self._assert_msisdns_free(user)
        self._by_id[str(user.id)] = user
        self._track(user)

    def save(self, user: User) -> None:
        self._assert_msisdns_free(user)
        self._by_id[str(user.id)] = user
        self._track(user)


class InMemoryWalletRepository(_Tracking):
    def __init__(self) -> None:
        super().__init__()
        self._by_id: dict[str, Wallet] = {}

    def get(self, wallet_id: EntityId) -> Wallet | None:
        wallet = self._by_id.get(str(wallet_id))
        if wallet is not None:
            self._track(wallet)
        return wallet

    def get_for_user(self, user_id: EntityId, currency: Currency) -> Wallet | None:
        for wallet in self._by_id.values():
            if wallet.user_id == user_id and wallet.currency == currency:
                self._track(wallet)
                return wallet
        return None

    def list_for_user(self, user_id: EntityId) -> list[Wallet]:
        found = [w for w in self._by_id.values() if w.user_id == user_id]
        for wallet in found:
            self._track(wallet)
        return found

    def get_for_update(self, wallet_id: EntityId) -> Wallet:
        wallet = self._by_id.get(str(wallet_id))
        if wallet is None:
            raise KeyError(wallet_id)
        self._track(wallet)
        return wallet

    def add(self, wallet: Wallet) -> None:
        self._by_id[str(wallet.id)] = wallet
        self._track(wallet)

    def save(self, wallet: Wallet) -> None:
        self._by_id[str(wallet.id)] = wallet
        self._track(wallet)


class InMemoryLedgerRepository:
    def __init__(self) -> None:
        self._by_id: dict[str, LedgerTransaction] = {}
        self._accounts: dict[tuple[str, str, str | None], EntityId] = {}
        self._account_seq = 0

    def add(self, transaction: LedgerTransaction) -> None:
        self._by_id[str(transaction.id)] = transaction

    def get(self, transaction_id: EntityId) -> LedgerTransaction | None:
        return self._by_id.get(str(transaction_id))

    def get_by_reference(self, reference: str) -> list[LedgerTransaction]:
        return [t for t in self._by_id.values() if t.reference == reference]

    def list_for_wallet(
        self, wallet_id: EntityId, *, limit: int = 50, before: EntityId | None = None
    ) -> Iterable[LedgerTransaction]:
        return self.list_for_wallets([wallet_id], limit=limit, before=before)

    def list_for_wallets(
        self, wallet_ids: list[EntityId], *, limit: int = 50, before: EntityId | None = None
    ) -> list[LedgerTransaction]:
        wanted = {str(w) for w in wallet_ids}
        matched = [
            t
            for t in self._by_id.values()
            if any(p.wallet_id is not None and str(p.wallet_id) in wanted for p in t.postings)
        ]
        matched.sort(key=lambda t: str(t.id), reverse=True)
        if before is not None:
            matched = [t for t in matched if str(t.id) < str(before)]
        return matched[:limit]

    def ensure_account(
        self,
        *,
        account_type: AccountType,
        currency: Currency,
        owner_ref: str | None = None,
    ) -> EntityId:
        key = (account_type.value, currency.code, owner_ref)
        if key not in self._accounts:
            self._account_seq += 1
            self._accounts[key] = EntityId(f"{self._account_seq:08d}-0000-0000-0000-000000000000")
        return self._accounts[key]

    @property
    def transactions(self) -> list[LedgerTransaction]:
        return list(self._by_id.values())


class InMemoryAgentRepository(_Tracking):
    def __init__(self) -> None:
        super().__init__()
        self._by_id: dict[str, Agent] = {}

    def get(self, agent_id: EntityId) -> Agent | None:
        agent = self._by_id.get(str(agent_id))
        if agent is not None:
            self._track(agent)
        return agent

    def get_by_user_id(self, user_id: EntityId) -> Agent | None:
        for agent in self._by_id.values():
            if agent.user_id == user_id:
                self._track(agent)
                return agent
        return None

    def get_for_update(self, agent_id: EntityId) -> Agent:
        agent = self._by_id.get(str(agent_id))
        if agent is None:
            raise KeyError(agent_id)
        self._track(agent)
        return agent

    def add(self, agent: Agent) -> None:
        self._by_id[str(agent.id)] = agent
        self._track(agent)

    def save(self, agent: Agent) -> None:
        self._by_id[str(agent.id)] = agent
        self._track(agent)


class InMemoryCashOrderRepository(_Tracking):
    def __init__(self) -> None:
        super().__init__()
        self._by_id: dict[str, CashOrder] = {}

    def get(self, order_id: EntityId) -> CashOrder | None:
        order = self._by_id.get(str(order_id))
        if order is not None:
            self._track(order)
        return order

    def get_pending_withdrawal_by_code_hash(self, code_hash: str) -> CashOrder | None:
        for order in self._by_id.values():
            if (
                order.type is CashOrderType.WITHDRAWAL
                and order.status is CashOrderStatus.INITIATED
                and order.code_hash == code_hash
            ):
                self._track(order)
                return order
        return None

    def add(self, order: CashOrder) -> None:
        self._by_id[str(order.id)] = order
        self._track(order)

    def save(self, order: CashOrder) -> None:
        self._by_id[str(order.id)] = order
        self._track(order)


class InMemoryKycCaseRepository(_Tracking):
    def __init__(self) -> None:
        super().__init__()
        self._by_id: dict[str, KycCase] = {}

    def get(self, case_id: EntityId) -> KycCase | None:
        case = self._by_id.get(str(case_id))
        if case is not None:
            self._track(case)
        return case

    def get_pending_for_user(self, user_id: EntityId) -> KycCase | None:
        for case in self._by_id.values():
            if case.user_id == user_id and case.status is KycCaseStatus.PENDING:
                self._track(case)
                return case
        return None

    def list_for_user(self, user_id: EntityId) -> list[KycCase]:
        cases = [c for c in self._by_id.values() if c.user_id == user_id]
        cases.sort(key=lambda c: c.submitted_at, reverse=True)
        for case in cases:
            self._track(case)
        return cases

    def add(self, case: KycCase) -> None:
        self._by_id[str(case.id)] = case
        self._track(case)

    def save(self, case: KycCase) -> None:
        self._by_id[str(case.id)] = case
        self._track(case)


class InMemoryPaymentRequestRepository(_Tracking):
    def __init__(self) -> None:
        super().__init__()
        self._by_id: dict[str, PaymentRequest] = {}

    def get(self, request_id: EntityId) -> PaymentRequest | None:
        request = self._by_id.get(str(request_id))
        if request is not None:
            self._track(request)
        return request

    def _recent(self, rows: list[PaymentRequest]) -> list[PaymentRequest]:
        rows.sort(key=lambda r: r.created_at, reverse=True)
        for r in rows:
            self._track(r)
        return rows

    def list_incoming(self, payer_id: EntityId) -> list[PaymentRequest]:
        return self._recent([r for r in self._by_id.values() if r.payer_id == payer_id])

    def list_outgoing(self, requester_id: EntityId) -> list[PaymentRequest]:
        return self._recent([r for r in self._by_id.values() if r.requester_id == requester_id])

    def add(self, request: PaymentRequest) -> None:
        self._by_id[str(request.id)] = request
        self._track(request)

    def save(self, request: PaymentRequest) -> None:
        self._by_id[str(request.id)] = request
        self._track(request)


class InMemoryMerchantRepository(_Tracking):
    def __init__(self) -> None:
        super().__init__()
        self._by_id: dict[str, Merchant] = {}

    def get(self, merchant_id: EntityId) -> Merchant | None:
        merchant = self._by_id.get(str(merchant_id))
        if merchant is not None:
            self._track(merchant)
        return merchant

    def get_by_user_id(self, user_id: EntityId) -> Merchant | None:
        for merchant in self._by_id.values():
            if merchant.user_id == user_id:
                self._track(merchant)
                return merchant
        return None

    def add(self, merchant: Merchant) -> None:
        self._by_id[str(merchant.id)] = merchant
        self._track(merchant)

    def save(self, merchant: Merchant) -> None:
        self._by_id[str(merchant.id)] = merchant
        self._track(merchant)


class InMemoryMerchantChargeRepository(_Tracking):
    def __init__(self) -> None:
        super().__init__()
        self._by_id: dict[str, MerchantCharge] = {}

    def get(self, charge_id: EntityId) -> MerchantCharge | None:
        charge = self._by_id.get(str(charge_id))
        if charge is not None:
            self._track(charge)
        return charge

    def get_for_update(self, charge_id: EntityId) -> MerchantCharge:
        charge = self._by_id.get(str(charge_id))
        if charge is None:
            raise KeyError(charge_id)
        self._track(charge)
        return charge

    def list_for_merchant(self, merchant_id: EntityId) -> list[MerchantCharge]:
        rows = [c for c in self._by_id.values() if c.merchant_id == merchant_id]
        rows.sort(key=lambda c: c.created_at, reverse=True)
        for c in rows:
            self._track(c)
        return rows

    def add(self, charge: MerchantCharge) -> None:
        self._by_id[str(charge.id)] = charge
        self._track(charge)

    def save(self, charge: MerchantCharge) -> None:
        self._by_id[str(charge.id)] = charge
        self._track(charge)


class InMemoryMerchantPaymentRepository(_Tracking):
    def __init__(self) -> None:
        super().__init__()
        self._by_id: dict[str, MerchantPayment] = {}

    def get(self, payment_id: EntityId) -> MerchantPayment | None:
        payment = self._by_id.get(str(payment_id))
        if payment is not None:
            self._track(payment)
        return payment

    def get_by_ledger_transaction_id(self, txn_id: EntityId) -> MerchantPayment | None:
        for payment in self._by_id.values():
            if payment.ledger_transaction_id == txn_id:
                self._track(payment)
                return payment
        return None

    def list_for_merchant(self, merchant_id: EntityId) -> list[MerchantPayment]:
        rows = [p for p in self._by_id.values() if p.merchant_id == merchant_id]
        rows.sort(key=lambda p: p.created_at, reverse=True)
        for p in rows:
            self._track(p)
        return rows

    def add(self, payment: MerchantPayment) -> None:
        self._by_id[str(payment.id)] = payment
        self._track(payment)

    def save(self, payment: MerchantPayment) -> None:
        self._by_id[str(payment.id)] = payment
        self._track(payment)


class InMemoryUnitOfWork:
    """Frontière transactionnelle en mémoire."""

    def __init__(
        self,
        *,
        users: InMemoryUserRepository | None = None,
        wallets: InMemoryWalletRepository | None = None,
        ledger: InMemoryLedgerRepository | None = None,
        agents: InMemoryAgentRepository | None = None,
        cash_orders: InMemoryCashOrderRepository | None = None,
        kyc_cases: InMemoryKycCaseRepository | None = None,
        payment_requests: InMemoryPaymentRequestRepository | None = None,
        merchants: InMemoryMerchantRepository | None = None,
        merchant_charges: InMemoryMerchantChargeRepository | None = None,
        merchant_payments: InMemoryMerchantPaymentRepository | None = None,
    ) -> None:
        self.users = users or InMemoryUserRepository()
        self.wallets = wallets or InMemoryWalletRepository()
        self.ledger = ledger or InMemoryLedgerRepository()
        self.agents = agents or InMemoryAgentRepository()
        self.cash_orders = cash_orders or InMemoryCashOrderRepository()
        self.kyc_cases = kyc_cases or InMemoryKycCaseRepository()
        self.payment_requests = payment_requests or InMemoryPaymentRequestRepository()
        self.merchants = merchants or InMemoryMerchantRepository()
        self.merchant_charges = merchant_charges or InMemoryMerchantChargeRepository()
        self.merchant_payments = merchant_payments or InMemoryMerchantPaymentRepository()
        self.committed = False
        self.rolled_back = False
        self._extra_events: list[DomainEvent] = []

    def __enter__(self) -> InMemoryUnitOfWork:
        self.committed = False
        self.rolled_back = False
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc_type is not None and not self.committed:
            self.rollback()

    def commit(self) -> None:
        self.committed = True

    def add_event(self, event: DomainEvent) -> None:
        self._extra_events.append(event)

    def rollback(self) -> None:
        self.rolled_back = True

    def collect_new_events(self) -> list[DomainEvent]:
        events: list[DomainEvent] = []
        for aggregate in (
            *self.users.seen,
            *self.wallets.seen,
            *self.agents.seen,
            *self.cash_orders.seen,
            *self.kyc_cases.seen,
            *self.payment_requests.seen,
            *self.merchants.seen,
            *self.merchant_charges.seen,
            *self.merchant_payments.seen,
        ):
            events.extend(aggregate.pull_events())
        events.extend(self._extra_events)
        self._extra_events = []
        return events


__all__ = [
    "InMemoryAgentRepository",
    "InMemoryCashOrderRepository",
    "InMemoryKycCaseRepository",
    "InMemoryLedgerRepository",
    "InMemoryMerchantChargeRepository",
    "InMemoryMerchantPaymentRepository",
    "InMemoryMerchantRepository",
    "InMemoryPaymentRequestRepository",
    "InMemoryUnitOfWork",
    "InMemoryUserRepository",
    "InMemoryWalletRepository",
]
