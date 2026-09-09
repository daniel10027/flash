"""Agrégat ``Agent`` — point cash détenant une réserve d'e-money (*float*).

Le float est un compte du ledger (``AGENT_FLOAT``) ; l'agrégat en tient la projection
(``float_available``). Un agent **décaisse** de l'e-money vers un client lors d'un dépôt
cash (son float baisse) et **encaisse** de l'e-money lors d'un retrait cash (son float
remonte, plafonné par ``float_cap``). Il perçoit une commission sur chaque opération.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from flash.domain.agent.events import (
    AgentAttachedToMaster,
    AgentCommissionAccrued,
    AgentCommissionPaid,
    AgentEnrolled,
    AgentFloatCollected,
    AgentFloatDisbursed,
    AgentFloatToppedUp,
    AgentFloatWithdrawn,
    AgentSuspended,
)
from flash.domain.shared.errors import AgentFloatTooLow, InvalidAccountState, InvalidInput
from flash.domain.shared.events import EventRecorder
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import Currency, Money

_MAX_COMMISSION_BPS = 2_000  # 20 %


class AgentStatus(StrEnum):
    ACTIVE = "ACTIVE"
    SUSPENDED = "SUSPENDED"


class Agent(EventRecorder):
    def __init__(
        self,
        *,
        id: EntityId,
        user_id: EntityId,
        currency: Currency,
        float_available: Money,
        float_cap: Money,
        commission_bps: int,
        created_at: datetime,
        status: AgentStatus = AgentStatus.ACTIVE,
        parent_agent_id: EntityId | None = None,
        commission_earned: Money | None = None,
        commission_paid: Money | None = None,
    ) -> None:
        super().__init__()
        for label, m in (("float_available", float_available), ("float_cap", float_cap)):
            if m.currency != currency:
                raise ValueError(f"{label} n'est pas dans la devise de l'agent.")
            if m.is_negative:
                raise ValueError(f"{label} ne peut pas être négatif.")
        if not 0 <= commission_bps <= _MAX_COMMISSION_BPS:
            raise ValueError("commission_bps hors bornes (0 à 2000).")
        self.id = id
        self.user_id = user_id
        self.currency = currency
        self.float_available = float_available
        self.float_cap = float_cap
        self.commission_bps = commission_bps
        self.created_at = created_at
        self.status = status
        self.parent_agent_id = parent_agent_id
        self.commission_earned = commission_earned or Money.zero(currency)
        self.commission_paid = commission_paid or Money.zero(currency)

    @classmethod
    def enroll(
        cls,
        *,
        agent_id: EntityId,
        user_id: EntityId,
        currency: Currency,
        float_cap: Money,
        commission_bps: int,
        now: datetime,
        initial_float: Money | None = None,
    ) -> Agent:
        agent = cls(
            id=agent_id,
            user_id=user_id,
            currency=currency,
            float_available=initial_float or Money.zero(currency),
            float_cap=float_cap,
            commission_bps=commission_bps,
            created_at=now,
        )
        agent.record_event(
            AgentEnrolled(
                occurred_at=now,
                aggregate_id=str(agent_id),
                user_id=str(user_id),
                currency=currency.code,
            )
        )
        return agent

    # ------------------------------------------------------------- garde-fous
    def ensure_active(self) -> None:
        if self.status is not AgentStatus.ACTIVE:
            raise InvalidAccountState("Cet agent est suspendu.", status=self.status.value)

    def _guard(self, amount: Money) -> None:
        if amount.currency != self.currency:
            raise ValueError("Devise du montant différente de celle de l'agent.")
        if not amount.is_positive:
            raise ValueError("Le montant doit être strictement positif.")

    # -------------------------------------------------------------- mouvements
    def disburse_float(self, amount: Money, now: datetime) -> None:
        """L'agent remet de l'e-money à un client (dépôt cash) : son float diminue."""
        self._guard(amount)
        self.ensure_active()
        if self.float_available < amount:
            raise AgentFloatTooLow(
                available=self.float_available.amount_minor, requested=amount.amount_minor
            )
        self.float_available = self.float_available - amount
        self.record_event(
            AgentFloatDisbursed(
                occurred_at=now, aggregate_id=str(self.id), amount_minor=amount.amount_minor
            )
        )

    def collect_float(self, amount: Money, now: datetime) -> None:
        """L'agent reprend de l'e-money (retrait cash) : son float remonte (≤ float_cap)."""
        self._guard(amount)
        self.ensure_active()
        if self.float_available + amount > self.float_cap:
            raise AgentFloatTooLow(
                "Plafond de float de l'agent dépassé.",
                available=self.float_available.amount_minor,
                cap=self.float_cap.amount_minor,
                requested=amount.amount_minor,
            )
        self.float_available = self.float_available + amount
        self.record_event(
            AgentFloatCollected(
                occurred_at=now, aggregate_id=str(self.id), amount_minor=amount.amount_minor
            )
        )

    def top_up_float(self, amount: Money, now: datetime) -> None:
        """L'agent achète de l'e-money auprès de Flash : son float monte (≤ float_cap)."""
        self._guard(amount)
        self.ensure_active()
        if self.float_available + amount > self.float_cap:
            raise AgentFloatTooLow(
                "Plafond de float de l'agent dépassé.",
                available=self.float_available.amount_minor,
                cap=self.float_cap.amount_minor,
                requested=amount.amount_minor,
            )
        self.float_available = self.float_available + amount
        self.record_event(
            AgentFloatToppedUp(
                occurred_at=now,
                aggregate_id=str(self.id),
                amount_minor=amount.amount_minor,
                float_after_minor=self.float_available.amount_minor,
            )
        )

    def withdraw_float(self, amount: Money, now: datetime) -> None:
        """L'agent restitue de l'e-money à Flash : son float baisse (remboursé en banque)."""
        self._guard(amount)
        self.ensure_active()
        if self.float_available < amount:
            raise AgentFloatTooLow(
                available=self.float_available.amount_minor, requested=amount.amount_minor
            )
        self.float_available = self.float_available - amount
        self.record_event(
            AgentFloatWithdrawn(
                occurred_at=now,
                aggregate_id=str(self.id),
                amount_minor=amount.amount_minor,
                float_after_minor=self.float_available.amount_minor,
            )
        )

    def commission_for(self, amount: Money) -> Money:
        """Commission de l'agent sur une opération (arrondie vers le bas)."""
        from decimal import ROUND_FLOOR

        return amount.percentage(self.commission_bps, rounding=ROUND_FLOOR)

    def accrue_commission(self, amount: Money, now: datetime) -> None:
        self._guard(amount)
        self.commission_earned = self.commission_earned + amount
        self.record_event(
            AgentCommissionAccrued(
                occurred_at=now, aggregate_id=str(self.id), amount_minor=amount.amount_minor
            )
        )

    @property
    def commission_owed(self) -> Money:
        """Commission gagnée non encore versée sur le portefeuille de l'agent."""
        return self.commission_earned - self.commission_paid

    def pay_commission(self, amount: Money, now: datetime) -> None:
        """Verse ``amount`` de commission due (déduit du float, à créditer sur le wallet)."""
        self._guard(amount)
        self.ensure_active()
        if amount > self.commission_owed:
            raise InvalidInput("Montant supérieur à la commission due.")
        if amount > self.float_available:
            raise AgentFloatTooLow(
                available=self.float_available.amount_minor, requested=amount.amount_minor
            )
        self.float_available = self.float_available - amount
        self.commission_paid = self.commission_paid + amount
        self.record_event(
            AgentCommissionPaid(
                occurred_at=now, aggregate_id=str(self.id), amount_minor=amount.amount_minor
            )
        )

    def attach_to_master(self, master_id: EntityId, now: datetime) -> None:
        if master_id == self.id:
            raise InvalidInput("Un agent ne peut pas être son propre master.")
        self.parent_agent_id = master_id
        self.record_event(
            AgentAttachedToMaster(
                occurred_at=now, aggregate_id=str(self.id), master_agent_id=str(master_id)
            )
        )

    def suspend(self, reason: str, now: datetime) -> None:
        if self.status is AgentStatus.SUSPENDED:
            return
        self.status = AgentStatus.SUSPENDED
        self.record_event(AgentSuspended(occurred_at=now, aggregate_id=str(self.id), reason=reason))

    def __repr__(self) -> str:
        avail, cap = self.float_available.amount_minor, self.float_cap.amount_minor
        return f"Agent(id={self.id!s}, float={avail}/{cap})"


__all__ = ["Agent", "AgentStatus"]
