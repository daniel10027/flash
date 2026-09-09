"""Interop opérateurs : initier un envoi (BE-065) ou un rechargement (BE-066).

Ces cas d'usage **initient** l'opération (état ``PENDING``) puis rendent la main : la
résolution est faite par ``application/operators/callbacks.py`` sur le webhook opérateur.
Un envoi réserve immédiatement ``amount + fee`` sur le portefeuille ; un rechargement ne
touche au portefeuille qu'à la confirmation.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flash.application.idempotency import IdempotencyGuard
from flash.application.operators.ports import OperatorGateway
from flash.application.services import AppServices
from flash.application.transaction import execute_in_uow
from flash.application.unit_of_work import WorkUnitOfWork
from flash.application.use_case import Command, UseCase
from flash.domain.country.reference import ReferenceDirectory
from flash.domain.limits.limits import KycPolicy, LimitPolicy
from flash.domain.operators.transfer import OperatorTransfer, OperatorTransferDirection
from flash.domain.pricing.pricing import PricingService
from flash.domain.shared.errors import InvalidInput, OperatorGatewayRejected
from flash.domain.shared.identifiers import EntityId, IdempotencyKey, Msisdn
from flash.domain.shared.money import Money
from flash.domain.shared.operations import OperationType


@dataclass(frozen=True, slots=True)
class OperatorTransferReceipt:
    transfer_id: str
    reference: str
    direction: str
    operator: str
    msisdn_masked: str
    amount_minor: int
    fee_minor: int
    currency: str
    status: str
    wallet_available_after_minor: int
    external_ref: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "transfer_id": self.transfer_id,
            "reference": self.reference,
            "direction": self.direction,
            "operator": self.operator,
            "msisdn_masked": self.msisdn_masked,
            "amount_minor": self.amount_minor,
            "fee_minor": self.fee_minor,
            "currency": self.currency,
            "status": self.status,
            "wallet_available_after_minor": self.wallet_available_after_minor,
            "external_ref": self.external_ref,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> OperatorTransferReceipt:
        return cls(**{k: data[k] for k in cls.__dataclass_fields__})


def _resolve_operator(directory: ReferenceDirectory, *, country: Any, code: str) -> str:
    for operator in directory.operators(country):
        if operator.code == code and operator.active:
            return operator.code
    raise InvalidInput("Opérateur inconnu pour ce pays.")


def _load_user_wallet(uow: WorkUnitOfWork, user_id: str) -> tuple[Any, Any]:
    user = uow.users.get(EntityId(user_id))
    if user is None:  # pragma: no cover - jeton valide
        raise InvalidInput("Compte introuvable.")
    user.ensure_can_transact()
    wallets = uow.wallets.list_for_user(user.id)
    if not wallets:  # pragma: no cover
        raise InvalidInput("Aucun portefeuille pour ce compte.")
    wallet = uow.wallets.get_for_update(EntityId(str(wallets[0].id)))
    return user, wallet


# ============================================================== envoi (payout)
@dataclass(frozen=True, slots=True)
class SendToOperatorAccountCommand(Command):
    user_id: str
    operator: str
    msisdn: str
    amount_minor: int
    idempotency_key: str
    country: str | None = None


class SendToOperatorAccount(UseCase[SendToOperatorAccountCommand, OperatorTransferReceipt]):
    def __init__(
        self,
        *,
        services: AppServices,
        gateway: OperatorGateway,
        reference: ReferenceDirectory,
        pricing: PricingService,
        limits: LimitPolicy,
        kyc: KycPolicy,
    ) -> None:
        self._services = services
        self._gateway = gateway
        self._reference = reference
        self._pricing = pricing
        self._limits = limits
        self._kyc = kyc
        self._guard = IdempotencyGuard(services.idempotency)

    def execute(
        self, command: SendToOperatorAccountCommand
    ) -> OperatorTransferReceipt:
        if command.amount_minor <= 0:
            raise InvalidInput("Le montant doit être strictement positif.")
        try:
            key = IdempotencyKey(command.idempotency_key)
            msisdn = Msisdn(command.msisdn)
        except ValueError as exc:
            raise InvalidInput(str(exc)) from exc
        outcome = self._guard.run(
            key=key,
            subject=command.user_id,
            route="POST /v1/operators/payouts",
            produce=lambda: self._start(command, msisdn),
            rebuild=OperatorTransferReceipt.from_dict,
        )
        return outcome.result

    def _start(
        self, command: SendToOperatorAccountCommand, msisdn: Msisdn
    ) -> tuple[OperatorTransferReceipt, dict[str, Any]]:
        now = self._services.clock.now()
        transfer_id = self._services.ids.new_id()
        reference = f"OPO-{transfer_id}"
        captured: dict[str, Any] = {}

        def work(uow: WorkUnitOfWork) -> None:
            user, wallet = _load_user_wallet(uow, command.user_id)
            operator = _resolve_operator(
                self._reference, country=user.country, code=command.operator
            )
            amount = Money(command.amount_minor, wallet.currency)
            fee = self._pricing.fee_for(
                country=user.country, operation=OperationType.OPERATOR_PAYOUT, amount=amount
            ).total

            self._kyc.require(operation=OperationType.OPERATOR_PAYOUT, kyc_tier=user.kyc_tier)
            self._limits.check(
                user_id=user.id,
                country=user.country,
                kyc_tier=user.kyc_tier,
                operation=OperationType.OPERATOR_PAYOUT,
                amount=amount,
            )

            wallet.reserve(amount + fee, now)  # lève InsufficientFunds
            transfer = OperatorTransfer.start(
                transfer_id=transfer_id,
                user_id=user.id,
                wallet_id=EntityId(str(wallet.id)),
                operator=operator,
                direction=OperatorTransferDirection.PAYOUT,
                msisdn=msisdn,
                amount=amount,
                fee=fee,
                reference=reference,
                now=now,
            )
            ack = self._gateway.payout(
                operator=operator,
                msisdn=msisdn.value,
                amount_minor=amount.amount_minor,
                currency=wallet.currency.code,
                reference=reference,
            )
            if not ack.accepted:
                wallet.release(amount + fee, now)  # on rend la réserve avant de renoncer
                raise OperatorGatewayRejected(ack.reason or "Refus opérateur.")
            transfer.attach_external_ref(ack.external_ref)
            uow.operator_transfers.add(transfer)
            uow.wallets.save(wallet)
            captured.update(
                operator=operator,
                fee=fee.amount_minor,
                currency=wallet.currency.code,
                available_after=wallet.available.amount_minor,
                external_ref=ack.external_ref,
            )

        execute_in_uow(self._services.uow, self._services.events, work)
        receipt = OperatorTransferReceipt(
            transfer_id=str(transfer_id),
            reference=reference,
            direction="PAYOUT",
            operator=captured["operator"],
            msisdn_masked=msisdn.masked(),
            amount_minor=command.amount_minor,
            fee_minor=captured["fee"],
            currency=captured["currency"],
            status="PENDING",
            wallet_available_after_minor=captured["available_after"],
            external_ref=captured["external_ref"],
        )
        return receipt, receipt.to_dict()


# ============================================================== rechargement (collect)
@dataclass(frozen=True, slots=True)
class TopUpFromOperatorCommand(Command):
    user_id: str
    operator: str
    msisdn: str
    amount_minor: int
    idempotency_key: str


class TopUpFromOperator(UseCase[TopUpFromOperatorCommand, OperatorTransferReceipt]):
    def __init__(
        self,
        *,
        services: AppServices,
        gateway: OperatorGateway,
        reference: ReferenceDirectory,
        pricing: PricingService,
        limits: LimitPolicy,
        kyc: KycPolicy,
    ) -> None:
        self._services = services
        self._gateway = gateway
        self._reference = reference
        self._pricing = pricing
        self._limits = limits
        self._kyc = kyc
        self._guard = IdempotencyGuard(services.idempotency)

    def execute(self, command: TopUpFromOperatorCommand) -> OperatorTransferReceipt:
        if command.amount_minor <= 0:
            raise InvalidInput("Le montant doit être strictement positif.")
        try:
            key = IdempotencyKey(command.idempotency_key)
            msisdn = Msisdn(command.msisdn)
        except ValueError as exc:
            raise InvalidInput(str(exc)) from exc
        outcome = self._guard.run(
            key=key,
            subject=command.user_id,
            route="POST /v1/operators/topups",
            produce=lambda: self._start(command, msisdn),
            rebuild=OperatorTransferReceipt.from_dict,
        )
        return outcome.result

    def _start(
        self, command: TopUpFromOperatorCommand, msisdn: Msisdn
    ) -> tuple[OperatorTransferReceipt, dict[str, Any]]:
        now = self._services.clock.now()
        transfer_id = self._services.ids.new_id()
        reference = f"OPC-{transfer_id}"
        captured: dict[str, Any] = {}

        def work(uow: WorkUnitOfWork) -> None:
            user, wallet = _load_user_wallet(uow, command.user_id)
            operator = _resolve_operator(
                self._reference, country=user.country, code=command.operator
            )
            amount = Money(command.amount_minor, wallet.currency)
            fee = self._pricing.fee_for(
                country=user.country, operation=OperationType.OPERATOR_COLLECT, amount=amount
            ).total

            self._kyc.require(operation=OperationType.OPERATOR_COLLECT, kyc_tier=user.kyc_tier)
            self._limits.check(
                user_id=user.id,
                country=user.country,
                kyc_tier=user.kyc_tier,
                operation=OperationType.OPERATOR_COLLECT,
                amount=amount,
            )
            self._limits.check_balance_cap(
                country=user.country,
                kyc_tier=user.kyc_tier,
                operation=OperationType.OPERATOR_COLLECT,
                current_balance=wallet.balance,
                incoming=amount - fee,
            )

            transfer = OperatorTransfer.start(
                transfer_id=transfer_id,
                user_id=user.id,
                wallet_id=EntityId(str(wallet.id)),
                operator=operator,
                direction=OperatorTransferDirection.COLLECT,
                msisdn=msisdn,
                amount=amount,
                fee=fee,
                reference=reference,
                now=now,
            )
            ack = self._gateway.collect(
                operator=operator,
                msisdn=msisdn.value,
                amount_minor=amount.amount_minor,
                currency=wallet.currency.code,
                reference=reference,
            )
            if not ack.accepted:
                raise OperatorGatewayRejected(ack.reason or "Refus opérateur.")
            transfer.attach_external_ref(ack.external_ref)
            uow.operator_transfers.add(transfer)
            captured.update(
                operator=operator,
                fee=fee.amount_minor,
                currency=wallet.currency.code,
                available_after=wallet.available.amount_minor,
                external_ref=ack.external_ref,
            )

        execute_in_uow(self._services.uow, self._services.events, work)
        receipt = OperatorTransferReceipt(
            transfer_id=str(transfer_id),
            reference=reference,
            direction="COLLECT",
            operator=captured["operator"],
            msisdn_masked=msisdn.masked(),
            amount_minor=command.amount_minor,
            fee_minor=captured["fee"],
            currency=captured["currency"],
            status="PENDING",
            wallet_available_after_minor=captured["available_after"],
            external_ref=captured["external_ref"],
        )
        return receipt, receipt.to_dict()


# ============================================================== listing
@dataclass(frozen=True, slots=True)
class ListOperatorTransfersCommand(Command):
    user_id: str


@dataclass(frozen=True, slots=True)
class OperatorTransferLine:
    transfer_id: str
    reference: str
    direction: str
    operator: str
    amount_minor: int
    fee_minor: int
    currency: str
    status: str
    created_at: str
    resolved_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "transfer_id": self.transfer_id,
            "reference": self.reference,
            "direction": self.direction,
            "operator": self.operator,
            "amount_minor": self.amount_minor,
            "fee_minor": self.fee_minor,
            "currency": self.currency,
            "status": self.status,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
        }


class ListOperatorTransfers(
    UseCase[ListOperatorTransfersCommand, list[OperatorTransferLine]]
):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(
        self, command: ListOperatorTransfersCommand
    ) -> list[OperatorTransferLine]:
        with self._services.uow() as uow:
            rows = uow.operator_transfers.list_for_user(EntityId(command.user_id))
            return [
                OperatorTransferLine(
                    transfer_id=str(t.id),
                    reference=t.reference,
                    direction=t.direction.value,
                    operator=t.operator,
                    amount_minor=t.amount.amount_minor,
                    fee_minor=t.fee.amount_minor,
                    currency=t.currency_code,
                    status=t.status.value,
                    created_at=t.created_at.isoformat(),
                    resolved_at=t.resolved_at.isoformat() if t.resolved_at else None,
                )
                for t in rows
            ]


__all__ = [
    "ListOperatorTransfers",
    "ListOperatorTransfersCommand",
    "OperatorTransferLine",
    "OperatorTransferReceipt",
    "SendToOperatorAccount",
    "SendToOperatorAccountCommand",
    "TopUpFromOperator",
    "TopUpFromOperatorCommand",
]
