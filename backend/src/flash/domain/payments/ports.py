"""Port du sous-domaine des demandes de paiement."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from flash.domain.payments.request import PaymentRequest
from flash.domain.shared.identifiers import EntityId


@runtime_checkable
class PaymentRequestRepository(Protocol):
    def get(self, request_id: EntityId) -> PaymentRequest | None: ...

    def list_incoming(self, payer_id: EntityId) -> list[PaymentRequest]:
        """Demandes reçues par ``payer_id`` (les plus récentes d'abord)."""
        ...

    def list_outgoing(self, requester_id: EntityId) -> list[PaymentRequest]:
        """Demandes émises par ``requester_id`` (les plus récentes d'abord)."""
        ...

    def add(self, request: PaymentRequest) -> None: ...

    def save(self, request: PaymentRequest) -> None: ...


__all__ = ["PaymentRequestRepository"]
