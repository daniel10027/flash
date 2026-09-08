"""Vue applicative d'une Unit of Work : frontière transactionnelle + dépôts métier.

Étend le port ``domain.shared.ports.UnitOfWork`` en exposant les dépôts dont les cas
d'usage ont besoin. Les implémentations concrètes (``SqlAlchemyUnitOfWork``,
``InMemoryUnitOfWork`` de test) le satisfont structurellement.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from flash.domain.agent.ports import AgentRepository
from flash.domain.cash.ports import CashOrderRepository
from flash.domain.identity.ports import KycCaseRepository, UserRepository
from flash.domain.ledger.ports import LedgerRepository
from flash.domain.shared.events import DomainEvent
from flash.domain.wallet.ports import WalletRepository


@runtime_checkable
class WorkUnitOfWork(Protocol):
    # Propriétés en lecture seule : covariantes, donc un dépôt concret (sous-type du
    # port) satisfait le protocole.
    @property
    def users(self) -> UserRepository: ...

    @property
    def wallets(self) -> WalletRepository: ...

    @property
    def ledger(self) -> LedgerRepository: ...

    @property
    def agents(self) -> AgentRepository: ...

    @property
    def cash_orders(self) -> CashOrderRepository: ...

    @property
    def kyc_cases(self) -> KycCaseRepository: ...

    def __enter__(self) -> WorkUnitOfWork: ...

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None: ...

    def commit(self) -> None: ...

    def rollback(self) -> None: ...

    def add_event(self, event: DomainEvent) -> None: ...

    def collect_new_events(self) -> list[DomainEvent]: ...


__all__ = ["WorkUnitOfWork"]
