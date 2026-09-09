"""Dépôts et Unit of Work en mémoire pour les tests de la couche application.

Respectent les contrats des ports de ``flash.domain`` sans aucune I/O. Le suivi des
agrégats manipulés permet à ``InMemoryUnitOfWork.collect_new_events`` de récupérer les
événements après un cas d'usage.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from flash.domain.agent.agent import Agent
from flash.domain.card.authorization import CardAuthorization, CardAuthorizationStatus
from flash.domain.card.card import Card
from flash.domain.cash.order import CashOrder, CashOrderStatus, CashOrderType
from flash.domain.identity.kyc_case import KycCase, KycCaseStatus
from flash.domain.identity.user import User
from flash.domain.ledger.chart import AccountType
from flash.domain.ledger.transaction import LedgerTransaction
from flash.domain.merchants.charge import MerchantCharge, MerchantChargeStatus
from flash.domain.merchants.merchant import Merchant
from flash.domain.merchants.payment import MerchantPayment
from flash.domain.merchants.settlement import MerchantSettlement
from flash.domain.operators.transfer import OperatorTransfer
from flash.domain.payments.request import PaymentRequest, PaymentRequestStatus
from flash.domain.savings.plan import SavingsPlan, SavingsPlanStatus
from flash.domain.shared.errors import PhoneNumberAlreadyLinked
from flash.domain.shared.events import DomainEvent, EventRecorder
from flash.domain.shared.identifiers import EntityId, Msisdn
from flash.domain.shared.money import Currency, Money
from flash.domain.vault.vault import Vault
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

    def list_all(self, *, limit: int = 1000, after: EntityId | None = None) -> list[Wallet]:
        rows = sorted(self._by_id.values(), key=lambda w: str(w.id))
        if after is not None:
            rows = [w for w in rows if str(w.id) > str(after)]
        return rows[:limit]

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

    def wallet_balance(self, wallet_id: EntityId) -> int:
        total = 0
        for txn in self._by_id.values():
            for p in txn.postings:
                if p.wallet_id is not None and str(p.wallet_id) == str(wallet_id):
                    total += (
                        p.amount.amount_minor
                        if p.direction.value == "CREDIT"
                        else -p.amount.amount_minor
                    )
        return total

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

    def list_expired_withdrawals(self, now: datetime, *, limit: int = 500) -> list[CashOrder]:
        rows = [
            o
            for o in self._by_id.values()
            if o.type is CashOrderType.WITHDRAWAL
            and o.status is CashOrderStatus.INITIATED
            and o.expires_at is not None
            and o.expires_at < now
        ]
        rows.sort(key=lambda o: o.expires_at or now)
        for o in rows:
            self._track(o)
        return rows[:limit]

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

    def list_expired(self, now: datetime, *, limit: int = 500) -> list[PaymentRequest]:
        rows = [
            r
            for r in self._by_id.values()
            if r.status is PaymentRequestStatus.PENDING and r.expires_at < now
        ]
        rows.sort(key=lambda r: r.expires_at)
        for r in rows:
            self._track(r)
        return rows[:limit]

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

    def get_for_update(self, merchant_id: EntityId) -> Merchant:
        merchant = self._by_id.get(str(merchant_id))
        if merchant is None:
            raise KeyError(merchant_id)
        self._track(merchant)
        return merchant

    def list_due_for_settlement(
        self, now: datetime, *, limit: int = 500
    ) -> list[Merchant]:
        rows = [m for m in self._by_id.values() if m.due_for_settlement(now)]
        rows.sort(key=lambda m: m.next_settlement_at or now)
        for m in rows[:limit]:
            self._track(m)
        return rows[:limit]

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

    def list_expired(self, now: datetime, *, limit: int = 500) -> list[MerchantCharge]:
        rows = [
            c
            for c in self._by_id.values()
            if c.status is MerchantChargeStatus.PENDING and c.expires_at < now
        ]
        rows.sort(key=lambda c: c.expires_at)
        for c in rows:
            self._track(c)
        return rows[:limit]

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

    def list_settleable(self, merchant_id: EntityId) -> list[MerchantPayment]:
        rows = [
            p
            for p in self._by_id.values()
            if p.merchant_id == merchant_id and p.is_settleable
        ]
        rows.sort(key=lambda p: p.created_at)
        for p in rows:
            self._track(p)
        return rows

    def list_for_settlement(self, settlement_id: EntityId) -> list[MerchantPayment]:
        rows = [p for p in self._by_id.values() if p.settlement_id == settlement_id]
        rows.sort(key=lambda p: p.created_at)
        for p in rows:
            self._track(p)
        return rows

    def add(self, payment: MerchantPayment) -> None:
        self._by_id[str(payment.id)] = payment
        self._track(payment)

    def save(self, payment: MerchantPayment) -> None:
        self._by_id[str(payment.id)] = payment
        self._track(payment)


class InMemoryMerchantSettlementRepository(_Tracking):
    def __init__(self) -> None:
        super().__init__()
        self._by_id: dict[str, MerchantSettlement] = {}

    def get(self, settlement_id: EntityId) -> MerchantSettlement | None:
        settlement = self._by_id.get(str(settlement_id))
        if settlement is not None:
            self._track(settlement)
        return settlement

    def list_for_merchant(self, merchant_id: EntityId) -> list[MerchantSettlement]:
        rows = [s for s in self._by_id.values() if s.merchant_id == merchant_id]
        rows.sort(key=lambda s: s.created_at, reverse=True)
        for s in rows:
            self._track(s)
        return rows

    def add(self, settlement: MerchantSettlement) -> None:
        self._by_id[str(settlement.id)] = settlement
        self._track(settlement)

    def save(self, settlement: MerchantSettlement) -> None:
        self._by_id[str(settlement.id)] = settlement
        self._track(settlement)


class InMemoryVaultRepository(_Tracking):
    def __init__(self) -> None:
        super().__init__()
        self._by_wallet: dict[str, Vault] = {}

    def get_for_wallet(self, wallet_id: EntityId) -> Vault | None:
        vault = self._by_wallet.get(str(wallet_id))
        if vault is not None:
            self._track(vault)
        return vault

    def get_for_user(self, user_id: EntityId) -> Vault | None:
        for vault in self._by_wallet.values():
            if vault.user_id == user_id:
                self._track(vault)
                return vault
        return None

    def add(self, vault: Vault) -> None:
        self._by_wallet[str(vault.wallet_id)] = vault
        self._track(vault)

    def save(self, vault: Vault) -> None:
        self._by_wallet[str(vault.wallet_id)] = vault
        self._track(vault)


class InMemorySavingsPlanRepository(_Tracking):
    def __init__(self) -> None:
        super().__init__()
        self._by_id: dict[str, SavingsPlan] = {}

    def get(self, plan_id: EntityId) -> SavingsPlan | None:
        plan = self._by_id.get(str(plan_id))
        if plan is not None:
            self._track(plan)
        return plan

    def get_for_update(self, plan_id: EntityId) -> SavingsPlan:
        plan = self._by_id.get(str(plan_id))
        if plan is None:
            raise KeyError(plan_id)
        self._track(plan)
        return plan

    def list_for_user(self, user_id: EntityId) -> list[SavingsPlan]:
        rows = [p for p in self._by_id.values() if p.user_id == user_id]
        rows.sort(key=lambda p: p.created_at, reverse=True)
        for p in rows:
            self._track(p)
        return rows

    def list_active(
        self, *, limit: int = 500, after: EntityId | None = None
    ) -> list[SavingsPlan]:
        rows = sorted(
            (p for p in self._by_id.values() if p.status is SavingsPlanStatus.ACTIVE),
            key=lambda p: str(p.id),
        )
        if after is not None:
            rows = [p for p in rows if str(p.id) > str(after)]
        for p in rows[:limit]:
            self._track(p)
        return rows[:limit]

    def list_contributions_due(self, now: datetime, *, limit: int = 500) -> list[SavingsPlan]:
        rows = [p for p in self._by_id.values() if p.contribution_due(now)]
        rows.sort(key=lambda p: p.next_contribution_at or now)
        for p in rows[:limit]:
            self._track(p)
        return rows[:limit]

    def add(self, plan: SavingsPlan) -> None:
        self._by_id[str(plan.id)] = plan
        self._track(plan)

    def save(self, plan: SavingsPlan) -> None:
        self._by_id[str(plan.id)] = plan
        self._track(plan)


class InMemoryCardRepository(_Tracking):
    def __init__(self) -> None:
        super().__init__()
        self._by_id: dict[str, Card] = {}

    def get(self, card_id: EntityId) -> Card | None:
        card = self._by_id.get(str(card_id))
        if card is not None:
            self._track(card)
        return card

    def get_for_update(self, card_id: EntityId) -> Card:
        card = self._by_id.get(str(card_id))
        if card is None:
            raise KeyError(card_id)
        self._track(card)
        return card

    def get_by_pan_token(self, pan_token: str) -> Card | None:
        for card in self._by_id.values():
            if card.pan_token == pan_token:
                self._track(card)
                return card
        return None

    def list_for_user(self, user_id: EntityId) -> list[Card]:
        rows = [c for c in self._by_id.values() if c.user_id == user_id]
        rows.sort(key=lambda c: c.created_at, reverse=True)
        for c in rows:
            self._track(c)
        return rows

    def add(self, card: Card) -> None:
        self._by_id[str(card.id)] = card
        self._track(card)

    def save(self, card: Card) -> None:
        self._by_id[str(card.id)] = card
        self._track(card)


class InMemoryCardAuthorizationRepository(_Tracking):
    _SPEND = (CardAuthorizationStatus.AUTHORIZED, CardAuthorizationStatus.CAPTURED)

    def __init__(self) -> None:
        super().__init__()
        self._by_id: dict[str, CardAuthorization] = {}

    def get(self, auth_id: EntityId) -> CardAuthorization | None:
        auth = self._by_id.get(str(auth_id))
        if auth is not None:
            self._track(auth)
        return auth

    def get_by_authorization_id(self, authorization_id: str) -> CardAuthorization | None:
        for auth in self._by_id.values():
            if auth.authorization_id == authorization_id:
                self._track(auth)
                return auth
        return None

    def get_for_update_by_authorization_id(self, authorization_id: str) -> CardAuthorization:
        auth = self.get_by_authorization_id(authorization_id)
        if auth is None:
            raise KeyError(authorization_id)
        return auth

    def total_spent_since(self, card_id: EntityId, since: datetime) -> Money:
        total = 0
        currency = Currency.of("XOF")
        for auth in self._by_id.values():
            if auth.card_id == card_id and auth.created_at >= since and auth.status in self._SPEND:
                total += auth.amount.amount_minor
                currency = auth.amount.currency
        return Money(total, currency)

    def list_for_card(self, card_id: EntityId) -> list[CardAuthorization]:
        rows = [a for a in self._by_id.values() if a.card_id == card_id]
        rows.sort(key=lambda a: a.created_at, reverse=True)
        for a in rows:
            self._track(a)
        return rows

    def list_resolved(
        self, *, limit: int = 500, after: EntityId | None = None
    ) -> list[CardAuthorization]:
        rows = sorted(
            (
                a
                for a in self._by_id.values()
                if a.status
                in (CardAuthorizationStatus.CAPTURED, CardAuthorizationStatus.REFUNDED)
            ),
            key=lambda a: str(a.id),
        )
        if after is not None:
            rows = [a for a in rows if str(a.id) > str(after)]
        for a in rows[:limit]:
            self._track(a)
        return rows[:limit]

    def add(self, authorization: CardAuthorization) -> None:
        self._by_id[str(authorization.id)] = authorization
        self._track(authorization)

    def save(self, authorization: CardAuthorization) -> None:
        self._by_id[str(authorization.id)] = authorization
        self._track(authorization)


class InMemoryOperatorTransferRepository(_Tracking):
    def __init__(self) -> None:
        super().__init__()
        self._by_id: dict[str, OperatorTransfer] = {}

    def get(self, transfer_id: EntityId) -> OperatorTransfer | None:
        transfer = self._by_id.get(str(transfer_id))
        if transfer is not None:
            self._track(transfer)
        return transfer

    def get_by_reference(self, reference: str) -> OperatorTransfer | None:
        for transfer in self._by_id.values():
            if transfer.reference == reference:
                self._track(transfer)
                return transfer
        return None

    def get_for_update_by_reference(self, reference: str) -> OperatorTransfer:
        transfer = self.get_by_reference(reference)
        if transfer is None:
            raise KeyError(reference)
        return transfer

    def list_for_user(self, user_id: EntityId) -> list[OperatorTransfer]:
        rows = [t for t in self._by_id.values() if t.user_id == user_id]
        rows.sort(key=lambda t: t.created_at, reverse=True)
        for t in rows:
            self._track(t)
        return rows

    def add(self, transfer: OperatorTransfer) -> None:
        self._by_id[str(transfer.id)] = transfer
        self._track(transfer)

    def save(self, transfer: OperatorTransfer) -> None:
        self._by_id[str(transfer.id)] = transfer
        self._track(transfer)


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
        merchant_settlements: InMemoryMerchantSettlementRepository | None = None,
        vaults: InMemoryVaultRepository | None = None,
        savings: InMemorySavingsPlanRepository | None = None,
        cards: InMemoryCardRepository | None = None,
        card_authorizations: InMemoryCardAuthorizationRepository | None = None,
        operator_transfers: InMemoryOperatorTransferRepository | None = None,
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
        self.merchant_settlements = (
            merchant_settlements or InMemoryMerchantSettlementRepository()
        )
        self.vaults = vaults or InMemoryVaultRepository()
        self.savings = savings or InMemorySavingsPlanRepository()
        self.cards = cards or InMemoryCardRepository()
        self.card_authorizations = card_authorizations or InMemoryCardAuthorizationRepository()
        self.operator_transfers = (
            operator_transfers or InMemoryOperatorTransferRepository()
        )
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
            *self.merchant_settlements.seen,
            *self.vaults.seen,
            *self.savings.seen,
            *self.cards.seen,
            *self.card_authorizations.seen,
            *self.operator_transfers.seen,
        ):
            events.extend(aggregate.pull_events())
        events.extend(self._extra_events)
        self._extra_events = []
        return events


__all__ = [
    "InMemoryAgentRepository",
    "InMemoryCardAuthorizationRepository",
    "InMemoryCardRepository",
    "InMemoryCashOrderRepository",
    "InMemoryKycCaseRepository",
    "InMemoryLedgerRepository",
    "InMemoryMerchantChargeRepository",
    "InMemoryMerchantPaymentRepository",
    "InMemoryMerchantRepository",
    "InMemoryMerchantSettlementRepository",
    "InMemoryOperatorTransferRepository",
    "InMemoryPaymentRequestRepository",
    "InMemorySavingsPlanRepository",
    "InMemoryUnitOfWork",
    "InMemoryUserRepository",
    "InMemoryVaultRepository",
    "InMemoryWalletRepository",
]
