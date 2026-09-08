"""Agrégat ``CashOrder`` — dépôt ou retrait d'espèces en agence.

- **Dépôt** : à une seule étape. L'agent identifie le client, encaisse le cash et
  l'agrégat naît déjà ``CONFIRMED``.
- **Retrait** : à deux étapes. Le client ``initie`` (montant réservé sur son wallet, un
  code à usage unique est émis avec une échéance), puis un agent ``confirme`` en
  présentant le code, ou l'ordre ``expire`` / est ``annulé`` (la réserve est rendue).

Le code de retrait n'est pas stocké en clair : l'agrégat ne détient que la vérification
« le code présenté correspond-il ? », déléguée à l'appelant via un booléen.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from flash.domain.cash.events import (
    CashDepositCompleted,
    CashWithdrawalCancelled,
    CashWithdrawalConfirmed,
    CashWithdrawalExpired,
    CashWithdrawalInitiated,
)
from flash.domain.shared.errors import (
    InvalidAccountState,
    WithdrawalCodeExpired,
    WithdrawalCodeInvalid,
)
from flash.domain.shared.events import EventRecorder
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import Money


class CashOrderType(StrEnum):
    DEPOSIT = "DEPOSIT"
    WITHDRAWAL = "WITHDRAWAL"


class CashOrderStatus(StrEnum):
    INITIATED = "INITIATED"
    CONFIRMED = "CONFIRMED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


class CashOrder(EventRecorder):
    def __init__(
        self,
        *,
        id: EntityId,
        type: CashOrderType,
        client_id: EntityId,
        amount: Money,
        fee: Money,
        currency_code: str,
        status: CashOrderStatus,
        created_at: datetime,
        agent_id: EntityId | None = None,
        code_hash: str | None = None,
        expires_at: datetime | None = None,
        ledger_transaction_id: EntityId | None = None,
    ) -> None:
        super().__init__()
        if amount.currency.code != currency_code or fee.currency.code != currency_code:
            raise ValueError("Devises incohérentes dans l'ordre cash.")
        if not amount.is_positive:
            raise ValueError("Le montant doit être strictement positif.")
        if fee.is_negative:
            raise ValueError("Les frais ne peuvent pas être négatifs.")
        self.id = id
        self.type = type
        self.client_id = client_id
        self.amount = amount
        self.fee = fee
        self.currency_code = currency_code
        self.status = status
        self.created_at = created_at
        self.agent_id = agent_id
        self.code_hash = code_hash
        self.expires_at = expires_at
        self.ledger_transaction_id = ledger_transaction_id

    # ---------------------------------------------------------------- dépôt
    @classmethod
    def deposit(
        cls,
        *,
        order_id: EntityId,
        client_id: EntityId,
        agent_id: EntityId,
        amount: Money,
        ledger_transaction_id: EntityId,
        now: datetime,
    ) -> CashOrder:
        order = cls(
            id=order_id,
            type=CashOrderType.DEPOSIT,
            client_id=client_id,
            agent_id=agent_id,
            amount=amount,
            fee=Money.zero(amount.currency),
            currency_code=amount.currency.code,
            status=CashOrderStatus.CONFIRMED,
            created_at=now,
            ledger_transaction_id=ledger_transaction_id,
        )
        order.record_event(
            CashDepositCompleted(
                occurred_at=now,
                aggregate_id=str(order_id),
                client_id=str(client_id),
                agent_id=str(agent_id),
                amount_minor=amount.amount_minor,
                currency=amount.currency.code,
            )
        )
        return order

    # ------------------------------------------------------------- retrait
    @classmethod
    def initiate_withdrawal(
        cls,
        *,
        order_id: EntityId,
        client_id: EntityId,
        amount: Money,
        fee: Money,
        code_hash: str,
        expires_at: datetime,
        now: datetime,
    ) -> CashOrder:
        order = cls(
            id=order_id,
            type=CashOrderType.WITHDRAWAL,
            client_id=client_id,
            amount=amount,
            fee=fee,
            currency_code=amount.currency.code,
            status=CashOrderStatus.INITIATED,
            created_at=now,
            code_hash=code_hash,
            expires_at=expires_at,
        )
        order.record_event(
            CashWithdrawalInitiated(
                occurred_at=now,
                aggregate_id=str(order_id),
                client_id=str(client_id),
                amount_minor=amount.amount_minor,
                fee_minor=fee.amount_minor,
                currency=amount.currency.code,
            )
        )
        return order

    def confirm(
        self,
        *,
        agent_id: EntityId,
        code_matches: bool,
        ledger_transaction_id: EntityId,
        now: datetime,
    ) -> None:
        if self.type is not CashOrderType.WITHDRAWAL:
            raise InvalidAccountState("Seul un retrait se confirme.")
        if self.status is not CashOrderStatus.INITIATED:
            raise InvalidAccountState("Ce retrait n'est plus en attente.", status=self.status.value)
        if self.expires_at is not None and now > self.expires_at:
            raise WithdrawalCodeExpired()
        if not code_matches:
            raise WithdrawalCodeInvalid()
        self.status = CashOrderStatus.CONFIRMED
        self.agent_id = agent_id
        self.ledger_transaction_id = ledger_transaction_id
        self.record_event(
            CashWithdrawalConfirmed(
                occurred_at=now,
                aggregate_id=str(self.id),
                client_id=str(self.client_id),
                agent_id=str(agent_id),
                amount_minor=self.amount.amount_minor,
                fee_minor=self.fee.amount_minor,
                currency=self.currency_code,
            )
        )

    def cancel(self, now: datetime) -> None:
        if self.status is not CashOrderStatus.INITIATED:
            raise InvalidAccountState(
                "Ce retrait ne peut plus être annulé.", status=self.status.value
            )
        self.status = CashOrderStatus.CANCELLED
        self.record_event(CashWithdrawalCancelled(occurred_at=now, aggregate_id=str(self.id)))

    def expire(self, now: datetime) -> None:
        if self.status is not CashOrderStatus.INITIATED:
            return
        self.status = CashOrderStatus.EXPIRED
        self.record_event(CashWithdrawalExpired(occurred_at=now, aggregate_id=str(self.id)))

    @property
    def total(self) -> Money:
        return self.amount + self.fee


__all__ = ["CashOrder", "CashOrderStatus", "CashOrderType"]
