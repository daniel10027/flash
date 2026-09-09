"""Espace agent (BE-072/073/074) : approvisionnement / restitution de float, hiérarchie
master ↔ sous-agent, versement des commissions, tableau de bord et recherche client.

Le *float* d'un agent est un compte ``AGENT_FLOAT`` du ledger ; l'agrégat en tient la
projection. Les commissions gagnées sur chaque opération cash s'accumulent
(``commission_earned``) puis sont versées sur le portefeuille de l'agent
(``AGENT_FLOAT`` → ``CLIENT_LIABILITY``) à la demande ou par le job périodique.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flash.application.cash.operations import NotAnAgent
from flash.application.idempotency import IdempotencyGuard
from flash.application.services import AppServices
from flash.application.transaction import execute_in_uow
from flash.application.unit_of_work import WorkUnitOfWork
from flash.application.use_case import Command, UseCase
from flash.domain.agent.agent import Agent
from flash.domain.ledger.chart import AccountType
from flash.domain.ledger.transaction import LedgerTransaction
from flash.domain.shared.errors import InvalidInput
from flash.domain.shared.identifiers import EntityId, IdempotencyKey, Msisdn
from flash.domain.shared.money import Money


# --------------------------------------------------------------------- vues
@dataclass(frozen=True, slots=True)
class AgentOverview:
    agent_id: str
    status: str
    currency: str
    float_available_minor: int
    float_cap_minor: int
    commission_bps: int
    commission_earned_minor: int
    commission_paid_minor: int
    commission_owed_minor: int
    parent_agent_id: str | None

    @classmethod
    def of(cls, agent: Agent) -> AgentOverview:
        return cls(
            agent_id=str(agent.id),
            status=agent.status.value,
            currency=agent.currency.code,
            float_available_minor=agent.float_available.amount_minor,
            float_cap_minor=agent.float_cap.amount_minor,
            commission_bps=agent.commission_bps,
            commission_earned_minor=agent.commission_earned.amount_minor,
            commission_paid_minor=agent.commission_paid.amount_minor,
            commission_owed_minor=agent.commission_owed.amount_minor,
            parent_agent_id=str(agent.parent_agent_id) if agent.parent_agent_id else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "status": self.status,
            "currency": self.currency,
            "float_available_minor": self.float_available_minor,
            "float_cap_minor": self.float_cap_minor,
            "commission_bps": self.commission_bps,
            "commission_earned_minor": self.commission_earned_minor,
            "commission_paid_minor": self.commission_paid_minor,
            "commission_owed_minor": self.commission_owed_minor,
            "parent_agent_id": self.parent_agent_id,
        }


@dataclass(frozen=True, slots=True)
class AgentOperationLine:
    order_id: str
    type: str
    status: str
    amount_minor: int
    currency: str
    created_at: str
    ledger_transaction_id: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "order_id": self.order_id,
            "type": self.type,
            "status": self.status,
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "created_at": self.created_at,
            "ledger_transaction_id": self.ledger_transaction_id,
        }


@dataclass(frozen=True, slots=True)
class CustomerLookupView:
    user_id: str
    msisdn_masked: str
    status: str
    kyc_tier: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "msisdn_masked": self.msisdn_masked,
            "status": self.status,
            "kyc_tier": self.kyc_tier,
        }


def _load_agent(uow: WorkUnitOfWork, agent_user_id: str) -> Agent:
    agent = uow.agents.get_by_user_id(EntityId(agent_user_id))
    if agent is None:
        raise NotAnAgent()
    return agent


def _agent_float_account(uow: WorkUnitOfWork, agent: Agent) -> EntityId:
    return uow.ledger.ensure_account(
        account_type=AccountType.AGENT_FLOAT,
        currency=agent.currency,
        owner_ref=str(agent.id),
    )


# =========================================================== float top-up / withdraw
@dataclass(frozen=True, slots=True)
class AgentFloatCommand(Command):
    agent_user_id: str
    amount_minor: int
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class AgentFloatReceipt:
    agent_id: str
    direction: str
    amount_minor: int
    currency: str
    float_available_after_minor: int
    ledger_transaction_id: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "direction": self.direction,
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "float_available_after_minor": self.float_available_after_minor,
            "ledger_transaction_id": self.ledger_transaction_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentFloatReceipt:
        return cls(**{k: data[k] for k in cls.__dataclass_fields__})


class _AgentFloatMove(UseCase[AgentFloatCommand, AgentFloatReceipt]):
    direction: str

    def __init__(self, *, services: AppServices) -> None:
        self._services = services
        self._guard = IdempotencyGuard(services.idempotency)

    def execute(self, command: AgentFloatCommand) -> AgentFloatReceipt:
        if command.amount_minor <= 0:
            raise InvalidInput("Le montant doit être strictement positif.")
        try:
            key = IdempotencyKey(command.idempotency_key)
        except ValueError as exc:
            raise InvalidInput(str(exc)) from exc
        outcome = self._guard.run(
            key=key,
            subject=command.agent_user_id,
            route=f"POST /v1/agent/float/{self.direction}",
            produce=lambda: self._run(command),
            rebuild=AgentFloatReceipt.from_dict,
        )
        return outcome.result

    def _run(
        self, command: AgentFloatCommand
    ) -> tuple[AgentFloatReceipt, dict[str, Any]]:
        now = self._services.clock.now()
        txn_id = self._services.ids.new_id()
        captured: dict[str, Any] = {}

        def work(uow: WorkUnitOfWork) -> None:
            agent = _load_agent(uow, command.agent_user_id)
            amount = Money(command.amount_minor, agent.currency)
            float_acc = _agent_float_account(uow, agent)
            bank_acc = uow.ledger.ensure_account(
                account_type=AccountType.BANK_SETTLEMENT, currency=agent.currency
            )
            if self.direction == "topup":
                agent.top_up_float(amount, now)
                txn = LedgerTransaction.agent_float_topup(
                    id=txn_id,
                    occurred_at=now,
                    reference=f"AFT-{txn_id}",
                    bank_settlement_account_id=bank_acc,
                    agent_float_account_id=float_acc,
                    amount=amount,
                )
            else:
                agent.withdraw_float(amount, now)
                txn = LedgerTransaction.agent_float_withdraw(
                    id=txn_id,
                    occurred_at=now,
                    reference=f"AFW-{txn_id}",
                    agent_float_account_id=float_acc,
                    bank_settlement_account_id=bank_acc,
                    amount=amount,
                )
            uow.ledger.add(txn)
            uow.agents.save(agent)
            captured.update(
                agent_id=str(agent.id),
                currency=agent.currency.code,
                float_after=agent.float_available.amount_minor,
            )

        execute_in_uow(self._services.uow, self._services.events, work)
        receipt = AgentFloatReceipt(
            agent_id=captured["agent_id"],
            direction=self.direction,
            amount_minor=command.amount_minor,
            currency=captured["currency"],
            float_available_after_minor=captured["float_after"],
            ledger_transaction_id=str(txn_id),
        )
        return receipt, receipt.to_dict()


class TopUpAgentFloat(_AgentFloatMove):
    direction = "topup"


class WithdrawAgentFloat(_AgentFloatMove):
    direction = "withdraw"


# =========================================================== hiérarchie
@dataclass(frozen=True, slots=True)
class AttachAgentToMasterCommand(Command):
    agent_id: str
    master_agent_id: str


class AttachAgentToMaster(UseCase[AttachAgentToMasterCommand, AgentOverview]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: AttachAgentToMasterCommand) -> AgentOverview:
        now = self._services.clock.now()
        captured: list[AgentOverview] = []

        def work(uow: WorkUnitOfWork) -> None:
            try:
                agent = uow.agents.get(EntityId(command.agent_id))
                master = uow.agents.get(EntityId(command.master_agent_id))
            except ValueError as exc:
                raise InvalidInput("Agent introuvable.") from exc
            if agent is None or master is None:
                raise InvalidInput("Agent introuvable.")
            agent.attach_to_master(master.id, now)
            uow.agents.save(agent)
            captured.append(AgentOverview.of(agent))

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


# =========================================================== commissions
@dataclass(frozen=True, slots=True)
class PayAgentCommissionCommand(Command):
    agent_user_id: str
    amount_minor: int | None = None


class PayAgentCommission(UseCase[PayAgentCommissionCommand, AgentOverview]):
    """Verse ``amount_minor`` (ou toute la commission due) sur le portefeuille de l'agent."""

    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: PayAgentCommissionCommand) -> AgentOverview:
        now = self._services.clock.now()
        txn_id = self._services.ids.new_id()
        captured: list[AgentOverview] = []

        def work(uow: WorkUnitOfWork) -> None:
            agent = _load_agent(uow, command.agent_user_id)
            owed = agent.commission_owed
            amount = (
                Money(command.amount_minor, agent.currency)
                if command.amount_minor is not None
                else owed
            )
            if not amount.is_positive:
                raise InvalidInput("Aucune commission à verser.")
            wallets = uow.wallets.list_for_user(agent.user_id)
            if not wallets:  # pragma: no cover - un agent a toujours un portefeuille
                raise InvalidInput("Aucun portefeuille pour cet agent.")
            wallet = uow.wallets.get_for_update(EntityId(str(wallets[0].id)))

            agent.pay_commission(amount, now)
            wallet_acc = uow.ledger.ensure_account(
                account_type=AccountType.CLIENT_LIABILITY,
                currency=agent.currency,
                owner_ref=str(agent.user_id),
            )
            uow.ledger.add(
                LedgerTransaction.agent_commission_payout(
                    id=txn_id,
                    occurred_at=now,
                    reference=f"ACP-{txn_id}",
                    agent_float_account_id=_agent_float_account(uow, agent),
                    agent_wallet_account_id=wallet_acc,
                    agent_wallet_id=wallet.id,
                    amount=amount,
                )
            )
            wallet.credit(amount, now)
            uow.wallets.save(wallet)
            uow.agents.save(agent)
            captured.append(AgentOverview.of(agent))

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


# =========================================================== lectures
@dataclass(frozen=True, slots=True)
class GetAgentOverviewCommand(Command):
    agent_user_id: str


class GetAgentOverview(UseCase[GetAgentOverviewCommand, AgentOverview]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: GetAgentOverviewCommand) -> AgentOverview:
        with self._services.uow() as uow:
            return AgentOverview.of(_load_agent(uow, command.agent_user_id))


@dataclass(frozen=True, slots=True)
class ListAgentOperationsCommand(Command):
    agent_user_id: str
    limit: int = 50


class ListAgentOperations(
    UseCase[ListAgentOperationsCommand, list[AgentOperationLine]]
):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(
        self, command: ListAgentOperationsCommand
    ) -> list[AgentOperationLine]:
        limit = max(1, min(command.limit, 200))
        with self._services.uow() as uow:
            agent = _load_agent(uow, command.agent_user_id)
            orders = uow.cash_orders.list_for_agent(agent.id, limit=limit)
            return [
                AgentOperationLine(
                    order_id=str(o.id),
                    type=o.type.value,
                    status=o.status.value,
                    amount_minor=o.amount.amount_minor,
                    currency=o.amount.currency.code,
                    created_at=o.created_at.isoformat(),
                    ledger_transaction_id=(
                        str(o.ledger_transaction_id) if o.ledger_transaction_id else None
                    ),
                )
                for o in orders
            ]


@dataclass(frozen=True, slots=True)
class LookupCustomerCommand(Command):
    agent_user_id: str
    phone_number: str
    country: str | None = None


class LookupCustomer(UseCase[LookupCustomerCommand, CustomerLookupView]):
    """Recherche d'un client par numéro : données minimales pour servir en agence."""

    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: LookupCustomerCommand) -> CustomerLookupView:
        try:
            from flash.domain.shared.identifiers import CountryCode

            cc = CountryCode(command.country.upper()) if command.country else None
            msisdn = Msisdn.parse(command.phone_number, default_country=cc)
        except ValueError as exc:
            raise InvalidInput(str(exc)) from exc
        with self._services.uow() as uow:
            _load_agent(uow, command.agent_user_id)
            user = uow.users.get_by_msisdn(msisdn)
            if user is None:
                raise InvalidInput("Aucun client pour ce numéro.")
            return CustomerLookupView(
                user_id=str(user.id),
                msisdn_masked=msisdn.masked(),
                status=user.status.value,
                kyc_tier=int(user.kyc_tier),
            )


__all__ = [
    "AgentFloatCommand",
    "AgentFloatReceipt",
    "AgentOperationLine",
    "AgentOverview",
    "AttachAgentToMaster",
    "AttachAgentToMasterCommand",
    "CustomerLookupView",
    "GetAgentOverview",
    "GetAgentOverviewCommand",
    "ListAgentOperations",
    "ListAgentOperationsCommand",
    "LookupCustomer",
    "LookupCustomerCommand",
    "PayAgentCommission",
    "PayAgentCommissionCommand",
    "TopUpAgentFloat",
    "WithdrawAgentFloat",
]
