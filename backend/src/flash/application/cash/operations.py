"""Cas d'usage cash : enrôlement d'agent, dépôt, retrait (initier / confirmer / annuler).

BE-034 (dépôt), BE-035 (initier retrait), BE-036 (confirmer retrait). Le dépôt et le
retrait sont **gratuits pour le client** (modèle Wave) ; l'agent perçoit une commission
payée par Flash. Toute écriture passe par une ``LedgerTransaction`` équilibrée.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from flash.application.cash.ports import WithdrawalCodes
from flash.application.idempotency import IdempotencyGuard
from flash.application.services import AppServices
from flash.application.transaction import execute_in_uow
from flash.application.unit_of_work import WorkUnitOfWork
from flash.application.use_case import Command, UseCase
from flash.domain.agent.agent import Agent
from flash.domain.cash.order import CashOrder
from flash.domain.identity.user import User
from flash.domain.ledger.chart import AccountType
from flash.domain.ledger.transaction import LedgerTransaction
from flash.domain.limits.limits import KycPolicy, LimitPolicy
from flash.domain.pricing.pricing import PricingService
from flash.domain.shared.errors import (
    InvalidAccountState,
    InvalidInput,
    RecipientNotFound,
    WithdrawalCodeInvalid,
)
from flash.domain.shared.identifiers import CountryCode, EntityId, IdempotencyKey, Msisdn
from flash.domain.shared.money import Money
from flash.domain.shared.operations import OperationType

_WITHDRAWAL_TTL = timedelta(minutes=15)
_OP_DEPOSIT = OperationType.CASH_DEPOSIT
_OP_WITHDRAWAL = OperationType.CASH_WITHDRAWAL


class NotAnAgent(InvalidAccountState):
    code = "NOT_AN_AGENT"
    message = "Ce compte n'est pas un agent."


def _ledger_accounts(
    uow: WorkUnitOfWork, *, client: User, agent: Agent, currency: Any
) -> dict[str, EntityId]:
    return {
        "client": uow.ledger.ensure_account(
            account_type=AccountType.CLIENT_LIABILITY, currency=currency, owner_ref=str(client.id)
        ),
        "agent_float": uow.ledger.ensure_account(
            account_type=AccountType.AGENT_FLOAT, currency=currency, owner_ref=str(agent.id)
        ),
        "fee_income": uow.ledger.ensure_account(
            account_type=AccountType.FLASH_FEE_INCOME, currency=currency
        ),
        "commission_expense": uow.ledger.ensure_account(
            account_type=AccountType.AGENT_COMMISSION_EXPENSE, currency=currency
        ),
    }


# ================================================================ enrôlement


@dataclass(frozen=True, slots=True)
class EnrollAgentCommand(Command):
    user_id: str
    float_cap_minor: int
    commission_bps: int = 100
    initial_float_minor: int = 0


@dataclass(frozen=True, slots=True)
class AgentView:
    agent_id: str
    float_available_minor: int
    float_cap_minor: int
    commission_bps: int
    status: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "float_available_minor": self.float_available_minor,
            "float_cap_minor": self.float_cap_minor,
            "commission_bps": self.commission_bps,
            "status": self.status,
        }


class EnrollAgent(UseCase[EnrollAgentCommand, AgentView]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: EnrollAgentCommand) -> AgentView:
        now = self._services.clock.now()
        agent_id = self._services.ids.new_id()
        captured: list[AgentView] = []

        def work(uow: WorkUnitOfWork) -> None:
            user = uow.users.get(EntityId(command.user_id))
            if user is None:
                raise InvalidInput("Compte introuvable.")
            if uow.agents.get_by_user_id(user.id) is not None:
                raise InvalidAccountState("Ce compte est déjà agent.")

            currency = _currency_of(uow, user)
            cap = Money(command.float_cap_minor, currency)
            initial = Money(max(command.initial_float_minor, 0), currency)
            agent = Agent.enroll(
                agent_id=agent_id,
                user_id=user.id,
                currency=currency,
                float_cap=cap,
                commission_bps=command.commission_bps,
                now=now,
                initial_float=initial,
            )
            if initial.is_positive:
                bank = uow.ledger.ensure_account(
                    account_type=AccountType.BANK_SETTLEMENT, currency=currency
                )
                float_acc = uow.ledger.ensure_account(
                    account_type=AccountType.AGENT_FLOAT, currency=currency, owner_ref=str(agent_id)
                )
                topup_id = self._services.ids.new_id()
                uow.ledger.add(
                    LedgerTransaction.agent_float_topup(
                        id=topup_id,
                        occurred_at=now,
                        reference=f"AFT-{topup_id}",
                        bank_settlement_account_id=bank,
                        agent_float_account_id=float_acc,
                        amount=initial,
                    )
                )
            uow.agents.add(agent)
            captured.append(_view(agent))

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


# ================================================================== dépôt


@dataclass(frozen=True, slots=True)
class CreateCashDepositCommand(Command):
    agent_user_id: str
    client_phone_number: str
    amount_minor: int
    idempotency_key: str
    country: str | None = None


@dataclass(frozen=True, slots=True)
class CashDepositReceipt:
    order_id: str
    amount_minor: int
    commission_minor: int
    currency: str
    client_masked: str
    agent_float_after_minor: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "amount_minor": self.amount_minor,
            "commission_minor": self.commission_minor,
            "currency": self.currency,
            "client_masked": self.client_masked,
            "agent_float_after_minor": self.agent_float_after_minor,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> CashDepositReceipt:
        return cls(**{k: data[k] for k in cls.__dataclass_fields__})


class CreateCashDeposit(UseCase[CreateCashDepositCommand, CashDepositReceipt]):
    def __init__(self, *, services: AppServices, limits: LimitPolicy, kyc: KycPolicy) -> None:
        self._services = services
        self._limits = limits
        self._kyc = kyc
        self._guard = IdempotencyGuard(services.idempotency)

    def execute(self, command: CreateCashDepositCommand) -> CashDepositReceipt:
        if command.amount_minor <= 0:
            raise InvalidInput("Le montant doit être strictement positif.")
        try:
            cc = CountryCode(command.country.upper()) if command.country else None
            client_msisdn = Msisdn.parse(command.client_phone_number, default_country=cc)
            key = IdempotencyKey(command.idempotency_key)
        except ValueError as exc:
            raise InvalidInput(str(exc)) from exc

        outcome = self._guard.run(
            key=key,
            subject=command.agent_user_id,
            route="POST /v1/agent/deposits",
            produce=lambda: self._deposit(command, client_msisdn),
            rebuild=CashDepositReceipt.from_dict,
        )
        return outcome.result

    def _deposit(
        self, command: CreateCashDepositCommand, client_msisdn: Msisdn
    ) -> tuple[CashDepositReceipt, dict[str, Any]]:
        now = self._services.clock.now()
        order_id = self._services.ids.new_id()
        txn_id = self._services.ids.new_id()
        captured: dict[str, Any] = {}

        def work(uow: WorkUnitOfWork) -> None:
            agent = _load_agent(uow, command.agent_user_id)
            client = uow.users.get_by_msisdn(client_msisdn)
            if client is None:
                raise RecipientNotFound(msisdn=client_msisdn.masked())
            client.ensure_can_transact()

            currency = agent.currency
            amount = Money(command.amount_minor, currency)
            client_wallet = uow.wallets.get_for_update(_primary_wallet_id(uow, client.id))

            self._kyc.require(operation=_OP_DEPOSIT, kyc_tier=client.kyc_tier)
            self._limits.check(
                user_id=client.id,
                country=client.country,
                kyc_tier=client.kyc_tier,
                operation=_OP_DEPOSIT,
                amount=amount,
            )
            self._limits.check_balance_cap(
                country=client.country,
                kyc_tier=client.kyc_tier,
                operation=_OP_DEPOSIT,
                current_balance=client_wallet.balance,
                incoming=amount,
            )

            commission = agent.commission_for(amount)
            acc = _ledger_accounts(uow, client=client, agent=agent, currency=currency)
            txn = LedgerTransaction.cash_in(
                id=txn_id,
                occurred_at=now,
                reference=f"DEP-{order_id}",
                agent_float_account_id=acc["agent_float"],
                client_account_id=acc["client"],
                client_wallet_id=client_wallet.id,
                amount=amount,
                commission=commission,
                agent_commission_expense_account_id=acc["commission_expense"],
            )
            uow.ledger.add(txn)

            agent.disburse_float(amount, now)
            if commission.is_positive:
                agent.collect_float(commission, now)
                agent.accrue_commission(commission, now)
            client_wallet.credit(amount, now)

            order = CashOrder.deposit(
                order_id=order_id,
                client_id=client.id,
                agent_id=agent.id,
                amount=amount,
                ledger_transaction_id=txn_id,
                now=now,
            )
            uow.cash_orders.add(order)
            uow.agents.save(agent)
            uow.wallets.save(client_wallet)
            captured.update(
                commission=commission.amount_minor,
                currency=currency.code,
                float_after=agent.float_available.amount_minor,
            )

        execute_in_uow(self._services.uow, self._services.events, work)
        receipt = CashDepositReceipt(
            order_id=str(order_id),
            amount_minor=command.amount_minor,
            commission_minor=captured["commission"],
            currency=captured["currency"],
            client_masked=client_msisdn.masked(),
            agent_float_after_minor=captured["float_after"],
        )
        return receipt, receipt.to_dict()


# ============================================================ retrait : initier


@dataclass(frozen=True, slots=True)
class InitiateWithdrawalCommand(Command):
    client_user_id: str
    amount_minor: int
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class WithdrawalTicket:
    order_id: str
    code: str  # affiché une seule fois au client
    amount_minor: int
    fee_minor: int
    currency: str
    expires_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "code": self.code,
            "amount_minor": self.amount_minor,
            "fee_minor": self.fee_minor,
            "currency": self.currency,
            "expires_at": self.expires_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WithdrawalTicket:
        return cls(**{k: data[k] for k in cls.__dataclass_fields__})


class InitiateCashWithdrawal(UseCase[InitiateWithdrawalCommand, WithdrawalTicket]):
    def __init__(
        self,
        *,
        services: AppServices,
        pricing: PricingService,
        limits: LimitPolicy,
        kyc: KycPolicy,
        codes: WithdrawalCodes,
    ) -> None:
        self._services = services
        self._pricing = pricing
        self._limits = limits
        self._kyc = kyc
        self._codes = codes
        self._guard = IdempotencyGuard(services.idempotency)

    def execute(self, command: InitiateWithdrawalCommand) -> WithdrawalTicket:
        if command.amount_minor <= 0:
            raise InvalidInput("Le montant doit être strictement positif.")
        try:
            key = IdempotencyKey(command.idempotency_key)
        except ValueError as exc:
            raise InvalidInput(str(exc)) from exc

        outcome = self._guard.run(
            key=key,
            subject=command.client_user_id,
            route="POST /v1/withdrawals",
            produce=lambda: self._initiate(command),
            rebuild=WithdrawalTicket.from_dict,
        )
        return outcome.result

    def _initiate(
        self, command: InitiateWithdrawalCommand
    ) -> tuple[WithdrawalTicket, dict[str, Any]]:
        now = self._services.clock.now()
        order_id = self._services.ids.new_id()
        code = self._codes.new_code()
        expires_at = now + _WITHDRAWAL_TTL
        captured: dict[str, Any] = {}

        def work(uow: WorkUnitOfWork) -> None:
            client = uow.users.get(EntityId(command.client_user_id))
            if client is None:
                raise InvalidInput("Compte introuvable.")
            client.ensure_can_transact()

            wallet = uow.wallets.get_for_update(_primary_wallet_id(uow, client.id))
            currency = wallet.currency
            amount = Money(command.amount_minor, currency)
            fee = self._pricing.fee_for(
                country=client.country, operation=_OP_WITHDRAWAL, amount=amount
            ).total
            self._kyc.require(operation=_OP_WITHDRAWAL, kyc_tier=client.kyc_tier)
            self._limits.check(
                user_id=client.id,
                country=client.country,
                kyc_tier=client.kyc_tier,
                operation=_OP_WITHDRAWAL,
                amount=amount,
            )

            wallet.reserve(amount + fee, now)  # lève InsufficientFunds si besoin
            order = CashOrder.initiate_withdrawal(
                order_id=order_id,
                client_id=client.id,
                amount=amount,
                fee=fee,
                code_hash=self._codes.fingerprint(code),
                expires_at=expires_at,
                now=now,
            )
            uow.cash_orders.add(order)
            uow.wallets.save(wallet)
            captured.update(fee=fee.amount_minor, currency=currency.code)

        execute_in_uow(self._services.uow, self._services.events, work)
        ticket = WithdrawalTicket(
            order_id=str(order_id),
            code=code,
            amount_minor=command.amount_minor,
            fee_minor=captured["fee"],
            currency=captured["currency"],
            expires_at=expires_at.isoformat(),
        )
        return ticket, ticket.to_dict()


# =========================================================== retrait : confirmer


@dataclass(frozen=True, slots=True)
class ConfirmWithdrawalCommand(Command):
    agent_user_id: str
    code: str


@dataclass(frozen=True, slots=True)
class WithdrawalConfirmation:
    order_id: str
    amount_minor: int
    commission_minor: int
    currency: str
    agent_float_after_minor: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "amount_minor": self.amount_minor,
            "commission_minor": self.commission_minor,
            "currency": self.currency,
            "agent_float_after_minor": self.agent_float_after_minor,
        }


class ConfirmCashWithdrawal(UseCase[ConfirmWithdrawalCommand, WithdrawalConfirmation]):
    def __init__(self, *, services: AppServices, codes: WithdrawalCodes) -> None:
        self._services = services
        self._codes = codes

    def execute(self, command: ConfirmWithdrawalCommand) -> WithdrawalConfirmation:
        code = command.code.strip()
        if not code:
            raise WithdrawalCodeInvalid()
        now = self._services.clock.now()
        txn_id = self._services.ids.new_id()
        captured: dict[str, Any] = {}

        def work(uow: WorkUnitOfWork) -> None:
            agent = _load_agent(uow, command.agent_user_id)
            order = uow.cash_orders.get_pending_withdrawal_by_code_hash(
                self._codes.fingerprint(code)
            )
            if order is None:
                raise WithdrawalCodeInvalid()

            client = uow.users.get(order.client_id)
            if client is None:  # pragma: no cover - intégrité
                raise WithdrawalCodeInvalid()
            wallet = uow.wallets.get_for_update(_primary_wallet_id(uow, client.id))
            currency = agent.currency

            commission = agent.commission_for(order.amount)
            acc = _ledger_accounts(uow, client=client, agent=agent, currency=currency)
            txn = LedgerTransaction.cash_out(
                id=txn_id,
                occurred_at=now,
                reference=f"WDL-{order.id}",
                client_account_id=acc["client"],
                client_wallet_id=wallet.id,
                agent_float_account_id=acc["agent_float"],
                fee_income_account_id=acc["fee_income"],
                amount=order.amount,
                fee=order.fee,
                commission=commission,
                agent_commission_expense_account_id=acc["commission_expense"],
            )
            uow.ledger.add(txn)

            wallet.settle_reservation(order.total, now)  # les fonds réservés quittent le wallet
            agent.collect_float(order.amount, now)
            if commission.is_positive:
                agent.collect_float(commission, now)
                agent.accrue_commission(commission, now)

            order.confirm(
                agent_id=agent.id, code_matches=True, ledger_transaction_id=txn_id, now=now
            )
            uow.cash_orders.save(order)
            uow.wallets.save(wallet)
            uow.agents.save(agent)
            captured.update(
                order_id=str(order.id),
                amount=order.amount.amount_minor,
                commission=commission.amount_minor,
                currency=currency.code,
                float_after=agent.float_available.amount_minor,
            )

        execute_in_uow(self._services.uow, self._services.events, work)
        return WithdrawalConfirmation(
            order_id=captured["order_id"],
            amount_minor=captured["amount"],
            commission_minor=captured["commission"],
            currency=captured["currency"],
            agent_float_after_minor=captured["float_after"],
        )


# =========================================================== retrait : annuler


@dataclass(frozen=True, slots=True)
class CancelWithdrawalCommand(Command):
    client_user_id: str
    order_id: str


class CancelCashWithdrawal(UseCase[CancelWithdrawalCommand, None]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: CancelWithdrawalCommand) -> None:
        now = self._services.clock.now()

        def work(uow: WorkUnitOfWork) -> None:
            order = uow.cash_orders.get(EntityId(command.order_id))
            if order is None or str(order.client_id) != command.client_user_id:
                raise InvalidInput("Retrait introuvable.")
            client = uow.users.get(order.client_id)
            if client is None:  # pragma: no cover
                raise InvalidInput("Compte introuvable.")
            wallet = uow.wallets.get_for_update(_primary_wallet_id(uow, client.id))
            order.cancel(now)  # lève InvalidAccountState si déjà confirmé/annulé
            wallet.release(order.total, now)
            uow.cash_orders.save(order)
            uow.wallets.save(wallet)

        execute_in_uow(self._services.uow, self._services.events, work)


# --------------------------------------------------------------------- helpers


def _load_agent(uow: WorkUnitOfWork, agent_user_id: str) -> Agent:
    agent = uow.agents.get_by_user_id(EntityId(agent_user_id))
    if agent is None:
        raise NotAnAgent()
    agent.ensure_active()
    return agent


def _primary_wallet_id(uow: WorkUnitOfWork, user_id: EntityId) -> EntityId:
    wallets = uow.wallets.list_for_user(user_id)
    if not wallets:  # pragma: no cover
        raise InvalidInput("Aucun portefeuille pour ce compte.")
    return EntityId(str(wallets[0].id))


def _currency_of(uow: WorkUnitOfWork, user: User) -> Any:
    wallets = uow.wallets.list_for_user(user.id)
    if not wallets:  # pragma: no cover
        raise InvalidInput("Aucun portefeuille pour ce compte.")
    return wallets[0].currency


def _view(agent: Agent) -> AgentView:
    return AgentView(
        agent_id=str(agent.id),
        float_available_minor=agent.float_available.amount_minor,
        float_cap_minor=agent.float_cap.amount_minor,
        commission_bps=agent.commission_bps,
        status=agent.status.value,
    )


__all__ = [
    "AgentView",
    "CancelCashWithdrawal",
    "CancelWithdrawalCommand",
    "CashDepositReceipt",
    "ConfirmCashWithdrawal",
    "ConfirmWithdrawalCommand",
    "CreateCashDeposit",
    "CreateCashDepositCommand",
    "EnrollAgent",
    "EnrollAgentCommand",
    "InitiateCashWithdrawal",
    "InitiateWithdrawalCommand",
    "NotAnAgent",
    "WithdrawalConfirmation",
    "WithdrawalTicket",
]
