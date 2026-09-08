"""Demandes de paiement entre utilisateurs (BE-032).

- ``CreatePaymentRequest`` : le *requester* réclame un montant à un *payer* (résolu par
  numéro). Idempotent. TTL 7 jours.
- ``AcceptPaymentRequest`` : le *payer* accepte → déclenche un ``SendP2PTransfer`` du
  *payer* vers le *requester*, puis note l'identifiant du transfert sur la demande.
- ``DeclinePaymentRequest`` (*payer*) / ``CancelPaymentRequest`` (*requester*).
- ``ListPaymentRequests`` : boîte de réception / d'envoi.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Literal

from flash.application.idempotency import IdempotencyGuard
from flash.application.services import AppServices
from flash.application.transaction import execute_in_uow
from flash.application.transfers.send_p2p import (
    SendP2PTransfer,
    SendP2PTransferCommand,
    TransferReceipt,
)
from flash.application.unit_of_work import WorkUnitOfWork
from flash.application.use_case import Command, UseCase
from flash.domain.payments.request import PaymentRequest, PaymentRequestStatus
from flash.domain.shared.errors import (
    InvalidAccountState,
    InvalidInput,
    RecipientNotFound,
    SelfTransfer,
)
from flash.domain.shared.identifiers import CountryCode, EntityId, IdempotencyKey, Msisdn
from flash.domain.shared.money import Money

_DEFAULT_TTL = timedelta(days=7)
Box = Literal["incoming", "outgoing"]


@dataclass(frozen=True, slots=True)
class PaymentRequestView:
    request_id: str
    requester_id: str
    payer_id: str
    amount_minor: int
    currency: str
    status: str
    note: str | None
    created_at: str
    expires_at: str
    resulting_transfer_id: str | None

    @classmethod
    def of(cls, request: PaymentRequest) -> PaymentRequestView:
        return cls(
            request_id=str(request.id),
            requester_id=str(request.requester_id),
            payer_id=str(request.payer_id),
            amount_minor=request.amount.amount_minor,
            currency=request.currency_code,
            status=request.status.value,
            note=request.note,
            created_at=request.created_at.isoformat(),
            expires_at=request.expires_at.isoformat(),
            resulting_transfer_id=(
                str(request.resulting_transfer_id) if request.resulting_transfer_id else None
            ),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "request_id": self.request_id,
            "requester_id": self.requester_id,
            "payer_id": self.payer_id,
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "status": self.status,
            "note": self.note,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "resulting_transfer_id": self.resulting_transfer_id,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PaymentRequestView:
        return cls(**{k: data[k] for k in cls.__dataclass_fields__})


# ------------------------------------------------------------------- créer
@dataclass(frozen=True, slots=True)
class CreatePaymentRequestCommand(Command):
    requester_user_id: str
    payer_phone_number: str
    amount_minor: int
    idempotency_key: str
    note: str | None = None
    country: str | None = None


class CreatePaymentRequest(UseCase[CreatePaymentRequestCommand, PaymentRequestView]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services
        self._guard = IdempotencyGuard(services.idempotency)

    def execute(self, command: CreatePaymentRequestCommand) -> PaymentRequestView:
        if command.amount_minor <= 0:
            raise InvalidInput("Le montant doit être strictement positif.")
        try:
            cc = CountryCode(command.country.upper()) if command.country else None
            payer_msisdn = Msisdn.parse(command.payer_phone_number, default_country=cc)
            key = IdempotencyKey(command.idempotency_key)
        except ValueError as exc:
            raise InvalidInput(str(exc)) from exc

        outcome = self._guard.run(
            key=key,
            subject=command.requester_user_id,
            route="POST /v1/payment-requests",
            produce=lambda: self._create(command, payer_msisdn),
            rebuild=PaymentRequestView.from_dict,
        )
        return outcome.result

    def _create(
        self, command: CreatePaymentRequestCommand, payer_msisdn: Msisdn
    ) -> tuple[PaymentRequestView, dict[str, Any]]:
        now = self._services.clock.now()
        request_id = self._services.ids.new_id()
        captured: list[PaymentRequestView] = []

        def work(uow: WorkUnitOfWork) -> None:
            requester = uow.users.get(EntityId(command.requester_user_id))
            if requester is None:  # pragma: no cover - jeton valide
                raise InvalidInput("Compte introuvable.")
            requester.ensure_can_transact()

            payer = uow.users.get_by_msisdn(payer_msisdn)
            if payer is None:
                raise RecipientNotFound(msisdn=payer_msisdn.masked())
            if payer.id == requester.id:
                raise SelfTransfer()

            wallets = uow.wallets.list_for_user(requester.id)
            if not wallets:  # pragma: no cover - un compte a toujours son wallet
                raise InvalidInput("Aucun portefeuille pour ce compte.")
            currency = wallets[0].currency

            request = PaymentRequest.open(
                request_id=request_id,
                requester_id=requester.id,
                payer_id=payer.id,
                amount=Money(command.amount_minor, currency),
                now=now,
                expires_at=now + _DEFAULT_TTL,
                note=command.note,
            )
            uow.payment_requests.add(request)
            captured.append(PaymentRequestView.of(request))

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0], captured[0].to_dict()


# ------------------------------------------------------------------- accepter
@dataclass(frozen=True, slots=True)
class AcceptPaymentRequestCommand(Command):
    payer_user_id: str
    request_id: str


@dataclass(frozen=True, slots=True)
class AcceptPaymentResult:
    request: PaymentRequestView
    transfer: TransferReceipt


class AcceptPaymentRequest(UseCase[AcceptPaymentRequestCommand, AcceptPaymentResult]):
    """Accepter une demande = régler un ``SendP2PTransfer`` du *payer* vers le *requester*.

    La clé d'idempotence du transfert est **dérivée de la demande** (``paymentreq-<id>``) :
    accepter deux fois la même demande ne déplace l'argent qu'une fois (le transfert
    rejoue son résultat mémorisé) et la demande reste ``ACCEPTED`` avec le même
    ``resulting_transfer_id``.
    """

    def __init__(self, *, services: AppServices, transfers: SendP2PTransfer) -> None:
        self._services = services
        self._transfers = transfers

    def execute(self, command: AcceptPaymentRequestCommand) -> AcceptPaymentResult:
        now = self._services.clock.now()
        payer_id = command.payer_user_id

        with self._services.uow() as uow:
            request = uow.payment_requests.get(EntityId(command.request_id))
            if request is None or str(request.payer_id) != payer_id:
                raise InvalidInput("Demande de paiement introuvable.")
            if request.status not in (
                PaymentRequestStatus.PENDING,
                PaymentRequestStatus.ACCEPTED,
            ):
                raise InvalidAccountState(
                    "Cette demande de paiement n'est plus en attente.",
                    status=request.status.value,
                )
            if request.status is PaymentRequestStatus.PENDING and now > request.expires_at:
                raise InvalidAccountState("Cette demande de paiement a expiré.", status="EXPIRED")
            requester = uow.users.get(request.requester_id)
            if requester is None:  # pragma: no cover - intégrité référentielle
                raise InvalidInput("Compte du demandeur introuvable.")
            requester_msisdn = requester.primary_phone_number.msisdn.value
            amount_minor = request.amount.amount_minor
            note = request.note

        receipt = self._transfers.execute(
            SendP2PTransferCommand(
                sender_user_id=payer_id,
                recipient_phone_number=requester_msisdn,
                amount_minor=amount_minor,
                idempotency_key=f"paymentreq-{command.request_id}",
                note=note,
            )
        )

        def work(uow: WorkUnitOfWork) -> None:
            request = uow.payment_requests.get(EntityId(command.request_id))
            assert request is not None  # chargée juste avant
            if request.status is PaymentRequestStatus.PENDING:
                request.accept(transfer_id=EntityId(receipt.transfer_id), now=now)
                uow.payment_requests.save(request)

        execute_in_uow(self._services.uow, self._services.events, work)

        with self._services.uow() as uow:
            final = uow.payment_requests.get(EntityId(command.request_id))
            assert final is not None
            return AcceptPaymentResult(request=PaymentRequestView.of(final), transfer=receipt)


# ------------------------------------------------------------------- refuser / annuler
@dataclass(frozen=True, slots=True)
class DeclinePaymentRequestCommand(Command):
    payer_user_id: str
    request_id: str


class DeclinePaymentRequest(UseCase[DeclinePaymentRequestCommand, PaymentRequestView]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: DeclinePaymentRequestCommand) -> PaymentRequestView:
        now = self._services.clock.now()
        captured: list[PaymentRequestView] = []

        def work(uow: WorkUnitOfWork) -> None:
            request = uow.payment_requests.get(EntityId(command.request_id))
            if request is None or str(request.payer_id) != command.payer_user_id:
                raise InvalidInput("Demande de paiement introuvable.")
            request.decline(now)
            uow.payment_requests.save(request)
            captured.append(PaymentRequestView.of(request))

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


@dataclass(frozen=True, slots=True)
class CancelPaymentRequestCommand(Command):
    requester_user_id: str
    request_id: str


class CancelPaymentRequest(UseCase[CancelPaymentRequestCommand, None]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: CancelPaymentRequestCommand) -> None:
        now = self._services.clock.now()

        def work(uow: WorkUnitOfWork) -> None:
            request = uow.payment_requests.get(EntityId(command.request_id))
            if request is None or str(request.requester_id) != command.requester_user_id:
                raise InvalidInput("Demande de paiement introuvable.")
            request.cancel(now)
            uow.payment_requests.save(request)

        execute_in_uow(self._services.uow, self._services.events, work)


# ------------------------------------------------------------------- lister
@dataclass(frozen=True, slots=True)
class ListPaymentRequestsCommand(Command):
    user_id: str
    box: Box = "incoming"


class ListPaymentRequests(UseCase[ListPaymentRequestsCommand, list[PaymentRequestView]]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: ListPaymentRequestsCommand) -> list[PaymentRequestView]:
        with self._services.uow() as uow:
            uid = EntityId(command.user_id)
            requests = (
                uow.payment_requests.list_incoming(uid)
                if command.box == "incoming"
                else uow.payment_requests.list_outgoing(uid)
            )
            return [PaymentRequestView.of(r) for r in requests]


__all__ = [
    "AcceptPaymentRequest",
    "AcceptPaymentRequestCommand",
    "AcceptPaymentResult",
    "CancelPaymentRequest",
    "CancelPaymentRequestCommand",
    "CreatePaymentRequest",
    "CreatePaymentRequestCommand",
    "DeclinePaymentRequest",
    "DeclinePaymentRequestCommand",
    "ListPaymentRequests",
    "ListPaymentRequestsCommand",
    "PaymentRequestView",
]
