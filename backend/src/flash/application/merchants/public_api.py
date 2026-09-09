"""API marchande publique (BE-071) : authentification par clé d'API + lecture de l'état
d'une demande de paiement.

La création de demande et le remboursement réutilisent tels quels ``CreateMerchantCharge``
et ``RefundMerchantPayment`` (l'appelant fournit ``merchant.user_id`` résolu depuis la
clé d'API).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flash.application.merchants.api_keys import MerchantApiKeyVault
from flash.application.services import AppServices
from flash.application.transaction import execute_in_uow
from flash.application.unit_of_work import WorkUnitOfWork
from flash.application.use_case import Command, UseCase
from flash.domain.shared.errors import (
    InvalidAccountState,
    InvalidInput,
    MerchantApiKeyInvalid,
)
from flash.domain.shared.identifiers import EntityId


@dataclass(frozen=True, slots=True)
class MerchantPrincipal:
    merchant_id: str
    merchant_user_id: str
    display_name: str
    currency: str


@dataclass(frozen=True, slots=True)
class AuthenticateMerchantApiKeyCommand(Command):
    presented_secret: str


class AuthenticateMerchantApiKey(
    UseCase[AuthenticateMerchantApiKeyCommand, MerchantPrincipal]
):
    """Résout un secret ``mk_…`` en marchand appelant et horodate la clé.

    Lève ``MerchantApiKeyInvalid`` (401) si la clé est inconnue, révoquée, ou si le
    marchand est suspendu / non vérifié (KYB).
    """

    def __init__(self, *, services: AppServices, vault: MerchantApiKeyVault) -> None:
        self._services = services
        self._vault = vault

    def execute(self, command: AuthenticateMerchantApiKeyCommand) -> MerchantPrincipal:
        prefix = self._vault.prefix_of(command.presented_secret)
        if not prefix:
            raise MerchantApiKeyInvalid()
        now = self._services.clock.now()
        captured: list[MerchantPrincipal] = []

        def work(uow: WorkUnitOfWork) -> None:
            key = uow.merchant_api_keys.get_by_prefix(prefix)
            if key is None or not key.is_active:
                raise MerchantApiKeyInvalid()
            if not self._vault.matches(command.presented_secret, key.secret_hash):
                raise MerchantApiKeyInvalid()
            merchant = uow.merchants.get(key.merchant_id)
            if merchant is None:  # pragma: no cover - intégrité référentielle
                raise MerchantApiKeyInvalid()
            try:
                merchant.ensure_active()
                merchant.ensure_kyb_approved()
            except InvalidAccountState as exc:
                raise MerchantApiKeyInvalid() from exc
            key.mark_used(now)
            uow.merchant_api_keys.save(key)
            captured.append(
                MerchantPrincipal(
                    merchant_id=str(merchant.id),
                    merchant_user_id=str(merchant.user_id),
                    display_name=merchant.display_name,
                    currency=merchant.currency.code,
                )
            )

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


@dataclass(frozen=True, slots=True)
class ChargeStatusView:
    charge_id: str
    merchant_id: str
    amount_minor: int
    currency: str
    reference: str
    status: str
    created_at: str
    expires_at: str
    payment_id: str | None
    paid_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "charge_id": self.charge_id,
            "merchant_id": self.merchant_id,
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "reference": self.reference,
            "status": self.status,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
            "payment_id": self.payment_id,
            "paid_at": self.paid_at,
        }


@dataclass(frozen=True, slots=True)
class GetMerchantChargeStatusCommand(Command):
    merchant_id: str
    charge_id: str


class GetMerchantChargeStatus(
    UseCase[GetMerchantChargeStatusCommand, ChargeStatusView]
):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: GetMerchantChargeStatusCommand) -> ChargeStatusView:
        with self._services.uow() as uow:
            try:
                charge = uow.merchant_charges.get(EntityId(command.charge_id))
            except ValueError as exc:
                raise InvalidInput("Demande de paiement introuvable.") from exc
            if charge is None or str(charge.merchant_id) != command.merchant_id:
                raise InvalidInput("Demande de paiement introuvable.")
            payment = None
            if charge.ledger_transaction_id is not None:
                payment = uow.merchant_payments.get_by_ledger_transaction_id(
                    charge.ledger_transaction_id
                )
            return ChargeStatusView(
                charge_id=str(charge.id),
                merchant_id=str(charge.merchant_id),
                amount_minor=charge.amount.amount_minor,
                currency=charge.currency_code,
                reference=charge.reference,
                status=charge.status.value,
                created_at=charge.created_at.isoformat(),
                expires_at=charge.expires_at.isoformat(),
                payment_id=str(payment.id) if payment else None,
                paid_at=payment.created_at.isoformat() if payment else None,
            )


__all__ = [
    "AuthenticateMerchantApiKey",
    "AuthenticateMerchantApiKeyCommand",
    "ChargeStatusView",
    "GetMerchantChargeStatus",
    "GetMerchantChargeStatusCommand",
    "MerchantPrincipal",
]
