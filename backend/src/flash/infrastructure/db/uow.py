"""``SqlAlchemyUnitOfWork`` — frontière transactionnelle sur une session SQLAlchemy.

À la sortie du bloc ``with`` :
- ``commit`` collecte les événements des agrégats manipulés, les écrit dans la table
  ``outbox`` (livraison fiable par un relais séparé) **dans la même transaction**, puis
  valide ;
- en cas d'exception, ``__exit__`` effectue le rollback ;
- la session est toujours refermée.

``collect_new_events`` renvoie ensuite les événements pour un éventuel envoi synchrone
best-effort (SSE, métriques) via l'``EventPublisher`` injecté au niveau applicatif.
"""

from __future__ import annotations

from typing import Self

from sqlalchemy.orm import Session, sessionmaker

from flash.domain.shared.events import DomainEvent, EventRecorder
from flash.domain.shared.ports import Clock
from flash.infrastructure.db.models import OutboxModel
from flash.infrastructure.db.repositories import (
    SqlAlchemyAgentRepository,
    SqlAlchemyCardAuthorizationRepository,
    SqlAlchemyCardRepository,
    SqlAlchemyCashOrderRepository,
    SqlAlchemyKycCaseRepository,
    SqlAlchemyLedgerRepository,
    SqlAlchemyMerchantChargeRepository,
    SqlAlchemyMerchantPaymentRepository,
    SqlAlchemyMerchantRepository,
    SqlAlchemyOperatorTransferRepository,
    SqlAlchemyPaymentRequestRepository,
    SqlAlchemySavingsPlanRepository,
    SqlAlchemyUserRepository,
    SqlAlchemyVaultRepository,
    SqlAlchemyWalletRepository,
)
from flash.infrastructure.ids import uuid7


class SqlAlchemyUnitOfWork:
    def __init__(self, session_factory: sessionmaker[Session], clock: Clock) -> None:
        self._session_factory = session_factory
        self._clock = clock
        self._session: Session | None = None
        self._tracked: list[EventRecorder] = []
        self._extra_events: list[DomainEvent] = []
        self._pending_events: list[DomainEvent] = []

    # ------------------------------------------------------------- contexte
    def __enter__(self) -> Self:
        self._session = self._session_factory()
        self._tracked = []
        self._extra_events = []
        self._pending_events = []
        self.users = SqlAlchemyUserRepository(self._session, self)
        self.wallets = SqlAlchemyWalletRepository(self._session, self)
        self.ledger = SqlAlchemyLedgerRepository(self._session)
        self.agents = SqlAlchemyAgentRepository(self._session, self)
        self.cash_orders = SqlAlchemyCashOrderRepository(self._session, self)
        self.kyc_cases = SqlAlchemyKycCaseRepository(self._session, self)
        self.payment_requests = SqlAlchemyPaymentRequestRepository(self._session, self)
        self.merchants = SqlAlchemyMerchantRepository(self._session, self)
        self.merchant_charges = SqlAlchemyMerchantChargeRepository(self._session, self)
        self.merchant_payments = SqlAlchemyMerchantPaymentRepository(self._session, self)
        self.vaults = SqlAlchemyVaultRepository(self._session, self)
        self.savings = SqlAlchemySavingsPlanRepository(self._session, self)
        self.cards = SqlAlchemyCardRepository(self._session, self)
        self.card_authorizations = SqlAlchemyCardAuthorizationRepository(self._session, self)
        self.operator_transfers = SqlAlchemyOperatorTransferRepository(self._session, self)
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        try:
            if exc_type is not None:
                self.rollback()
        finally:
            if self._session is not None:
                self._session.close()
                self._session = None

    # --------------------------------------------------------------- API port
    def track(self, aggregate: EventRecorder) -> None:
        if all(aggregate is not seen for seen in self._tracked):
            self._tracked.append(aggregate)

    def add_event(self, event: DomainEvent) -> None:
        """Ajoute un événement transverse (non porté par un agrégat unique)."""
        self._extra_events.append(event)

    def commit(self) -> None:
        session = self._require_session()
        events = self._drain_tracked_events()
        now = self._clock.now()
        for event in events:
            session.add(
                OutboxModel(
                    id=str(uuid7()),
                    event_name=event.name,
                    aggregate_id=event.aggregate_id,
                    payload=event.to_payload(),
                    occurred_at=event.occurred_at,
                    created_at=now,
                )
            )
        session.commit()
        self._pending_events = events

    def rollback(self) -> None:
        if self._session is not None:
            self._session.rollback()

    def collect_new_events(self) -> list[DomainEvent]:
        events = self._pending_events
        self._pending_events = []
        return events

    # ------------------------------------------------------------- interne
    def _require_session(self) -> Session:
        if self._session is None:
            raise RuntimeError("Unit of Work utilisée hors d'un bloc `with`.")
        return self._session

    def _drain_tracked_events(self) -> list[DomainEvent]:
        events: list[DomainEvent] = []
        for aggregate in self._tracked:
            events.extend(aggregate.pull_events())
        events.extend(self._extra_events)
        self._extra_events = []
        return events


__all__ = ["SqlAlchemyUnitOfWork"]
