"""Marchands : enrôlement, QR statique / dynamique, paiement (BE-033).

Le paiement marchand est **gratuit pour le client**. Le marchand paie ``fee_bps`` prélevé
sur le montant ; le net va sur ``MERCHANT_PAYABLE`` (dette de Flash envers le marchand),
soldé plus tard par un règlement (hors périmètre). Toute écriture passe par une
``LedgerTransaction`` équilibrée.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from flash.application.idempotency import IdempotencyGuard
from flash.application.services import AppServices
from flash.application.transaction import execute_in_uow
from flash.application.unit_of_work import WorkUnitOfWork
from flash.application.use_case import Command, UseCase
from flash.domain.ledger.chart import AccountType
from flash.domain.ledger.transaction import LedgerTransaction
from flash.domain.limits.limits import KycPolicy, LimitPolicy
from flash.domain.merchants.charge import MerchantCharge
from flash.domain.merchants.merchant import Merchant
from flash.domain.merchants.payment import MerchantPayment
from flash.domain.shared.errors import InvalidAccountState, InvalidInput
from flash.domain.shared.identifiers import EntityId, IdempotencyKey
from flash.domain.shared.money import Money
from flash.domain.shared.operations import OperationType

_OP = OperationType.MERCHANT_PAYMENT
_MAX_CHARGE_TTL_MINUTES = 24 * 60


class NotAMerchant(InvalidAccountState):
    code = "NOT_A_MERCHANT"
    message = "Ce compte n'est pas un marchand."


# ============================================================== enrôlement
@dataclass(frozen=True, slots=True)
class EnrollMerchantCommand(Command):
    user_id: str
    display_name: str
    category: str = "GENERAL"
    fee_bps: int = 100


@dataclass(frozen=True, slots=True)
class MerchantView:
    merchant_id: str
    display_name: str
    category: str
    currency: str
    fee_bps: int
    status: str
    static_qr_payload: str

    @classmethod
    def of(cls, merchant: Merchant) -> MerchantView:
        return cls(
            merchant_id=str(merchant.id),
            display_name=merchant.display_name,
            category=merchant.category,
            currency=merchant.currency.code,
            fee_bps=merchant.fee_bps,
            status=merchant.status.value,
            static_qr_payload=merchant.static_qr_payload(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "merchant_id": self.merchant_id,
            "display_name": self.display_name,
            "category": self.category,
            "currency": self.currency,
            "fee_bps": self.fee_bps,
            "status": self.status,
            "static_qr_payload": self.static_qr_payload,
        }


class EnrollMerchant(UseCase[EnrollMerchantCommand, MerchantView]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: EnrollMerchantCommand) -> MerchantView:
        if not command.display_name.strip():
            raise InvalidInput("Le nom commercial est requis.")
        now = self._services.clock.now()
        merchant_id = self._services.ids.new_id()
        captured: list[MerchantView] = []

        def work(uow: WorkUnitOfWork) -> None:
            user = uow.users.get(EntityId(command.user_id))
            if user is None:
                raise InvalidInput("Compte introuvable.")
            if uow.merchants.get_by_user_id(user.id) is not None:
                raise InvalidAccountState("Ce compte est déjà marchand.")
            wallets = uow.wallets.list_for_user(user.id)
            if not wallets:  # pragma: no cover - un compte a toujours son wallet
                raise InvalidInput("Aucun portefeuille pour ce compte.")
            merchant = Merchant.enroll(
                merchant_id=merchant_id,
                user_id=user.id,
                display_name=command.display_name,
                category=command.category,
                currency=wallets[0].currency,
                fee_bps=command.fee_bps,
                now=now,
            )
            uow.merchants.add(merchant)
            captured.append(MerchantView.of(merchant))

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


# ============================================================== QR
@dataclass(frozen=True, slots=True)
class GetMerchantQrCommand(Command):
    merchant_user_id: str


class GetMerchantQr(UseCase[GetMerchantQrCommand, MerchantView]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: GetMerchantQrCommand) -> MerchantView:
        with self._services.uow() as uow:
            merchant = uow.merchants.get_by_user_id(EntityId(command.merchant_user_id))
            if merchant is None:
                raise NotAMerchant()
            return MerchantView.of(merchant)


@dataclass(frozen=True, slots=True)
class CreateMerchantChargeCommand(Command):
    merchant_user_id: str
    amount_minor: int
    reference: str
    ttl_minutes: int = 60


@dataclass(frozen=True, slots=True)
class MerchantChargeView:
    charge_id: str
    merchant_id: str
    amount_minor: int
    currency: str
    reference: str
    status: str
    qr_payload: str
    created_at: str
    expires_at: str

    @classmethod
    def of(cls, charge: MerchantCharge) -> MerchantChargeView:
        return cls(
            charge_id=str(charge.id),
            merchant_id=str(charge.merchant_id),
            amount_minor=charge.amount.amount_minor,
            currency=charge.currency_code,
            reference=charge.reference,
            status=charge.status.value,
            qr_payload=charge.dynamic_qr_payload(),
            created_at=charge.created_at.isoformat(),
            expires_at=charge.expires_at.isoformat(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "charge_id": self.charge_id,
            "merchant_id": self.merchant_id,
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "reference": self.reference,
            "status": self.status,
            "qr_payload": self.qr_payload,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }


class CreateMerchantCharge(UseCase[CreateMerchantChargeCommand, MerchantChargeView]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: CreateMerchantChargeCommand) -> MerchantChargeView:
        if command.amount_minor <= 0:
            raise InvalidInput("Le montant doit être strictement positif.")
        if not command.reference.strip():
            raise InvalidInput("Une référence est requise.")
        ttl = max(1, min(command.ttl_minutes, _MAX_CHARGE_TTL_MINUTES))
        now = self._services.clock.now()
        charge_id = self._services.ids.new_id()
        captured: list[MerchantChargeView] = []

        def work(uow: WorkUnitOfWork) -> None:
            merchant = uow.merchants.get_by_user_id(EntityId(command.merchant_user_id))
            if merchant is None:
                raise NotAMerchant()
            merchant.ensure_active()
            charge = MerchantCharge.open(
                charge_id=charge_id,
                merchant_id=merchant.id,
                amount=Money(command.amount_minor, merchant.currency),
                reference=command.reference,
                now=now,
                expires_at=now + timedelta(minutes=ttl),
            )
            uow.merchant_charges.add(charge)
            captured.append(MerchantChargeView.of(charge))

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


# ============================================================== paiement
@dataclass(frozen=True, slots=True)
class PayMerchantCommand(Command):
    payer_user_id: str
    merchant_id: str
    idempotency_key: str
    amount_minor: int | None = None
    charge_id: str | None = None


@dataclass(frozen=True, slots=True)
class MerchantPaymentReceipt:
    payment_id: str
    merchant_id: str
    merchant_name: str
    amount_minor: int
    fee_minor: int
    currency: str
    reference: str
    payer_balance_after_minor: int
    occurred_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "payment_id": self.payment_id,
            "merchant_id": self.merchant_id,
            "merchant_name": self.merchant_name,
            "amount_minor": self.amount_minor,
            "fee_minor": self.fee_minor,
            "currency": self.currency,
            "reference": self.reference,
            "payer_balance_after_minor": self.payer_balance_after_minor,
            "occurred_at": self.occurred_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MerchantPaymentReceipt:
        return cls(**{k: data[k] for k in cls.__dataclass_fields__})


class PayMerchant(UseCase[PayMerchantCommand, MerchantPaymentReceipt]):
    def __init__(self, *, services: AppServices, limits: LimitPolicy, kyc: KycPolicy) -> None:
        self._services = services
        self._limits = limits
        self._kyc = kyc
        self._guard = IdempotencyGuard(services.idempotency)

    def execute(self, command: PayMerchantCommand) -> MerchantPaymentReceipt:
        try:
            key = IdempotencyKey(command.idempotency_key)
            merchant_id = EntityId(command.merchant_id)
        except ValueError as exc:
            raise InvalidInput(str(exc)) from exc
        if command.charge_id is None and (
            command.amount_minor is None or command.amount_minor <= 0
        ):
            raise InvalidInput("Montant requis pour un paiement par QR statique.")

        outcome = self._guard.run(
            key=key,
            subject=command.payer_user_id,
            route="POST /v1/merchant-payments",
            produce=lambda: self._pay(command, merchant_id),
            rebuild=MerchantPaymentReceipt.from_dict,
        )
        return outcome.result

    def _pay(
        self, command: PayMerchantCommand, merchant_id: EntityId
    ) -> tuple[MerchantPaymentReceipt, dict[str, Any]]:
        now = self._services.clock.now()
        txn_id = self._services.ids.new_id()
        payment_id = self._services.ids.new_id()
        captured: dict[str, Any] = {}

        def work(uow: WorkUnitOfWork) -> None:
            payer = uow.users.get(EntityId(command.payer_user_id))
            if payer is None:  # pragma: no cover - jeton valide
                raise InvalidInput("Compte introuvable.")
            payer.ensure_can_transact()

            merchant = uow.merchants.get(merchant_id)
            if merchant is None:
                raise NotAMerchant()
            merchant.ensure_active()
            if merchant.user_id == payer.id:
                raise InvalidInput("Un marchand ne peut pas se payer lui-même.")

            charge: MerchantCharge | None = None
            if command.charge_id is not None:
                charge = uow.merchant_charges.get_for_update(EntityId(command.charge_id))
                if charge.merchant_id != merchant.id:
                    raise InvalidInput("Cette demande n'appartient pas à ce marchand.")
                charge.ensure_payable(now)
                amount = charge.amount
                reference = charge.reference
            else:
                amount = Money(command.amount_minor or 0, merchant.currency)
                reference = f"QR-{payment_id}"

            wallets = uow.wallets.list_for_user(payer.id)
            if not wallets:  # pragma: no cover
                raise InvalidInput("Aucun portefeuille pour ce compte.")
            payer_wallet = uow.wallets.get_for_update(EntityId(str(wallets[0].id)))

            self._kyc.require(operation=_OP, kyc_tier=payer.kyc_tier)
            self._limits.check(
                user_id=payer.id,
                country=payer.country,
                kyc_tier=payer.kyc_tier,
                operation=_OP,
                amount=amount,
            )

            fee = merchant.fee_for(amount)
            payer_acc = uow.ledger.ensure_account(
                account_type=AccountType.CLIENT_LIABILITY,
                currency=merchant.currency,
                owner_ref=str(payer.id),
            )
            merchant_acc = uow.ledger.ensure_account(
                account_type=AccountType.MERCHANT_PAYABLE,
                currency=merchant.currency,
                owner_ref=str(merchant.id),
            )
            fee_acc = uow.ledger.ensure_account(
                account_type=AccountType.FLASH_FEE_INCOME, currency=merchant.currency
            )
            txn = LedgerTransaction.merchant_payment(
                id=txn_id,
                occurred_at=now,
                reference=f"MPY-{payment_id}",
                payer_account_id=payer_acc,
                payer_wallet_id=payer_wallet.id,
                merchant_payable_account_id=merchant_acc,
                fee_income_account_id=fee_acc,
                amount=amount,
                merchant_fee=fee,
                metadata={
                    "merchant_name": merchant.display_name,
                    "reference": reference,
                    "fee_minor": fee.amount_minor,
                },
            )
            uow.ledger.add(txn)
            payer_wallet.debit(amount, now)  # lève InsufficientFunds si besoin

            payment = MerchantPayment.record(
                payment_id=payment_id,
                payer_id=payer.id,
                merchant_id=merchant.id,
                amount=amount,
                fee=fee,
                reference=reference,
                ledger_transaction_id=txn_id,
                now=now,
                charge_id=charge.id if charge is not None else None,
            )
            uow.merchant_payments.add(payment)
            uow.wallets.save(payer_wallet)
            if charge is not None:
                charge.mark_paid(payer_id=payer.id, ledger_transaction_id=txn_id)
                uow.merchant_charges.save(charge)
            captured.update(
                merchant_name=merchant.display_name,
                amount=amount.amount_minor,
                fee=fee.amount_minor,
                currency=merchant.currency.code,
                reference=reference,
                balance_after=payer_wallet.available.amount_minor,
            )

        execute_in_uow(self._services.uow, self._services.events, work)
        receipt = MerchantPaymentReceipt(
            payment_id=str(payment_id),
            merchant_id=str(merchant_id),
            merchant_name=captured["merchant_name"],
            amount_minor=captured["amount"],
            fee_minor=captured["fee"],
            currency=captured["currency"],
            reference=captured["reference"],
            payer_balance_after_minor=captured["balance_after"],
            occurred_at=now.isoformat(),
        )
        return receipt, receipt.to_dict()


# ============================================================== listing
@dataclass(frozen=True, slots=True)
class ListMerchantPaymentsCommand(Command):
    merchant_user_id: str


@dataclass(frozen=True, slots=True)
class MerchantPaymentLine:
    payment_id: str
    amount_minor: int
    fee_minor: int
    net_minor: int
    currency: str
    reference: str
    status: str
    occurred_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "payment_id": self.payment_id,
            "amount_minor": self.amount_minor,
            "fee_minor": self.fee_minor,
            "net_minor": self.net_minor,
            "currency": self.currency,
            "reference": self.reference,
            "status": self.status,
            "occurred_at": self.occurred_at,
        }


class ListMerchantPayments(UseCase[ListMerchantPaymentsCommand, list[MerchantPaymentLine]]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: ListMerchantPaymentsCommand) -> list[MerchantPaymentLine]:
        with self._services.uow() as uow:
            merchant = uow.merchants.get_by_user_id(EntityId(command.merchant_user_id))
            if merchant is None:
                raise NotAMerchant()
            payments = uow.merchant_payments.list_for_merchant(merchant.id)
            return [
                MerchantPaymentLine(
                    payment_id=str(p.id),
                    amount_minor=p.amount.amount_minor,
                    fee_minor=p.fee.amount_minor,
                    net_minor=p.net_to_merchant.amount_minor,
                    currency=p.currency_code,
                    reference=p.reference,
                    status=p.status.value,
                    occurred_at=p.created_at.isoformat(),
                )
                for p in payments
            ]


__all__ = [
    "CreateMerchantCharge",
    "CreateMerchantChargeCommand",
    "EnrollMerchant",
    "EnrollMerchantCommand",
    "GetMerchantQr",
    "GetMerchantQrCommand",
    "ListMerchantPayments",
    "ListMerchantPaymentsCommand",
    "MerchantChargeView",
    "MerchantPaymentLine",
    "MerchantPaymentReceipt",
    "MerchantView",
    "NotAMerchant",
    "PayMerchant",
    "PayMerchantCommand",
]
