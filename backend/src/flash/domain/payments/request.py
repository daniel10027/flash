"""Agrégat ``PaymentRequest`` — un utilisateur (*requester*) réclame un paiement à un
autre (*payer*).

L'agrégat ne déplace **aucun** argent : il porte l'intention et sa machine à états.
``PENDING`` → ``ACCEPTED`` (le cas d'usage déclenche alors un ``SendP2PTransfer`` du
*payer* vers le *requester* et note l'identifiant du transfert) ou ``DECLINED`` /
``CANCELLED`` / ``EXPIRED``.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from flash.domain.payments.events import (
    PaymentRequestAccepted,
    PaymentRequestCancelled,
    PaymentRequestCreated,
    PaymentRequestDeclined,
    PaymentRequestExpired,
)
from flash.domain.shared.errors import InvalidAccountState, InvalidInput
from flash.domain.shared.events import EventRecorder
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import Money


class PaymentRequestStatus(StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    DECLINED = "DECLINED"
    CANCELLED = "CANCELLED"
    EXPIRED = "EXPIRED"


class PaymentRequest(EventRecorder):
    def __init__(
        self,
        *,
        id: EntityId,
        requester_id: EntityId,
        payer_id: EntityId,
        amount: Money,
        currency_code: str,
        status: PaymentRequestStatus,
        created_at: datetime,
        expires_at: datetime,
        note: str | None = None,
        resulting_transfer_id: EntityId | None = None,
    ) -> None:
        super().__init__()
        if amount.currency.code != currency_code:
            raise ValueError("Devise incohérente dans la demande de paiement.")
        if not amount.is_positive:
            raise ValueError("Le montant doit être strictement positif.")
        if requester_id == payer_id:
            raise InvalidInput("On ne peut pas se réclamer un paiement à soi-même.")
        self.id = id
        self.requester_id = requester_id
        self.payer_id = payer_id
        self.amount = amount
        self.currency_code = currency_code
        self.status = status
        self.created_at = created_at
        self.expires_at = expires_at
        self.note = note
        self.resulting_transfer_id = resulting_transfer_id

    @classmethod
    def open(
        cls,
        *,
        request_id: EntityId,
        requester_id: EntityId,
        payer_id: EntityId,
        amount: Money,
        now: datetime,
        expires_at: datetime,
        note: str | None = None,
    ) -> PaymentRequest:
        request = cls(
            id=request_id,
            requester_id=requester_id,
            payer_id=payer_id,
            amount=amount,
            currency_code=amount.currency.code,
            status=PaymentRequestStatus.PENDING,
            created_at=now,
            expires_at=expires_at,
            note=note,
        )
        request.record_event(
            PaymentRequestCreated(
                occurred_at=now,
                aggregate_id=str(request_id),
                requester_id=str(requester_id),
                payer_id=str(payer_id),
                amount_minor=amount.amount_minor,
                currency=amount.currency.code,
            )
        )
        return request

    # ------------------------------------------------------------- transitions
    def _ensure_pending(self, now: datetime) -> None:
        if self.status is not PaymentRequestStatus.PENDING:
            raise InvalidAccountState(
                "Cette demande de paiement n'est plus en attente.", status=self.status.value
            )
        if now > self.expires_at:
            raise InvalidAccountState("Cette demande de paiement a expiré.", status="EXPIRED")

    def accept(self, *, transfer_id: EntityId, now: datetime) -> None:
        self._ensure_pending(now)
        self.status = PaymentRequestStatus.ACCEPTED
        self.resulting_transfer_id = transfer_id
        self.record_event(
            PaymentRequestAccepted(
                occurred_at=now,
                aggregate_id=str(self.id),
                requester_id=str(self.requester_id),
                payer_id=str(self.payer_id),
                transfer_id=str(transfer_id),
            )
        )

    def decline(self, now: datetime) -> None:
        self._ensure_pending(now)
        self.status = PaymentRequestStatus.DECLINED
        self.record_event(
            PaymentRequestDeclined(
                occurred_at=now,
                aggregate_id=str(self.id),
                requester_id=str(self.requester_id),
                payer_id=str(self.payer_id),
            )
        )

    def cancel(self, now: datetime) -> None:
        self._ensure_pending(now)
        self.status = PaymentRequestStatus.CANCELLED
        self.record_event(
            PaymentRequestCancelled(
                occurred_at=now,
                aggregate_id=str(self.id),
                requester_id=str(self.requester_id),
                payer_id=str(self.payer_id),
            )
        )

    def expire(self, now: datetime) -> None:
        if self.status is not PaymentRequestStatus.PENDING:
            return
        self.status = PaymentRequestStatus.EXPIRED
        self.record_event(
            PaymentRequestExpired(
                occurred_at=now,
                aggregate_id=str(self.id),
                requester_id=str(self.requester_id),
                payer_id=str(self.payer_id),
            )
        )

    def __repr__(self) -> str:
        return (
            f"PaymentRequest(id={self.id!s}, {self.amount.amount_minor} "
            f"{self.currency_code}, status={self.status.value})"
        )


__all__ = ["PaymentRequest", "PaymentRequestStatus"]
