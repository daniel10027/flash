"""``RefundMerchantPayment`` (BE-037) — remboursement d'un paiement marchand.

Le marchand (propriétaire du compte) rembourse un paiement encaissé, dans la fenêtre
``reversal_window``. On contre-passe la ``LedgerTransaction`` d'origine (le payeur
récupère ``amount``, le net quitte ``MERCHANT_PAYABLE``, ``fee`` quitte
``FLASH_FEE_INCOME``) et le ``MerchantPayment`` passe ``REFUNDED``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta
from typing import Any

from flash.application.idempotency import IdempotencyGuard
from flash.application.merchants.operations import NotAMerchant
from flash.application.services import AppServices
from flash.application.transaction import execute_in_uow
from flash.application.unit_of_work import WorkUnitOfWork
from flash.application.use_case import Command, UseCase
from flash.domain.ledger.chart import Direction
from flash.domain.ledger.transaction import LedgerTransaction, TransactionKind
from flash.domain.shared.errors import DuplicateOperation, InvalidInput, ReversalWindowClosed
from flash.domain.shared.identifiers import EntityId, IdempotencyKey


@dataclass(frozen=True, slots=True)
class RefundMerchantPaymentCommand(Command):
    merchant_user_id: str
    payment_id: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class MerchantRefundReceipt:
    payment_id: str
    reversal_id: str
    amount_minor: int
    fee_minor: int
    currency: str
    status: str
    occurred_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "payment_id": self.payment_id,
            "reversal_id": self.reversal_id,
            "amount_minor": self.amount_minor,
            "fee_minor": self.fee_minor,
            "currency": self.currency,
            "status": self.status,
            "occurred_at": self.occurred_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MerchantRefundReceipt:
        return cls(**{k: data[k] for k in cls.__dataclass_fields__})


class RefundMerchantPayment(UseCase[RefundMerchantPaymentCommand, MerchantRefundReceipt]):
    def __init__(self, *, services: AppServices, window: timedelta) -> None:
        self._services = services
        self._window = window
        self._guard = IdempotencyGuard(services.idempotency)

    def execute(self, command: RefundMerchantPaymentCommand) -> MerchantRefundReceipt:
        try:
            key = IdempotencyKey(command.idempotency_key)
            payment_id = EntityId(command.payment_id)
        except ValueError as exc:
            raise InvalidInput(str(exc)) from exc

        outcome = self._guard.run(
            key=key,
            subject=command.merchant_user_id,
            route="POST /v1/merchant/payments/{id}/refund",
            produce=lambda: self._refund(command, payment_id),
            rebuild=MerchantRefundReceipt.from_dict,
        )
        return outcome.result

    def _refund(
        self, command: RefundMerchantPaymentCommand, payment_id: EntityId
    ) -> tuple[MerchantRefundReceipt, dict[str, Any]]:
        now = self._services.clock.now()
        reversal_id = self._services.ids.new_id()
        captured: dict[str, Any] = {}

        def work(uow: WorkUnitOfWork) -> None:
            merchant = uow.merchants.get_by_user_id(EntityId(command.merchant_user_id))
            if merchant is None:
                raise NotAMerchant()
            payment = uow.merchant_payments.get(payment_id)
            if payment is None or payment.merchant_id != merchant.id:
                raise InvalidInput("Paiement marchand introuvable.")

            original = uow.ledger.get(payment.ledger_transaction_id)
            if (
                original is None or original.kind is not TransactionKind.MERCHANT_PAYMENT
            ):  # pragma: no cover - intégrité référentielle
                raise InvalidInput("Écriture d'origine introuvable.")
            if now - original.occurred_at > self._window:
                raise ReversalWindowClosed()
            already = uow.ledger.get_by_reference(original.reference)
            if any(
                t.kind is TransactionKind.REVERSAL and t.reverses_transaction_id == original.id
                for t in already
            ):
                raise DuplicateOperation()

            payer_debit = next(
                p
                for p in original.postings
                if p.direction is Direction.DEBIT and p.wallet_id is not None
            )
            assert payer_debit.wallet_id is not None
            payer_wallet = uow.wallets.get_for_update(EntityId(str(payer_debit.wallet_id)))

            uow.ledger.add(
                LedgerTransaction.reversal(
                    id=reversal_id,
                    original=original,
                    occurred_at=now,
                    reason="Remboursement de paiement marchand",
                )
            )
            payer_wallet.credit(payment.amount, now)
            payment.refund(reversal_transaction_id=reversal_id, now=now)
            uow.wallets.save(payer_wallet)
            uow.merchant_payments.save(payment)
            captured.update(
                amount=payment.amount.amount_minor,
                fee=payment.fee.amount_minor,
                currency=payment.currency_code,
                status=payment.status.value,
            )

        execute_in_uow(self._services.uow, self._services.events, work)
        receipt = MerchantRefundReceipt(
            payment_id=str(payment_id),
            reversal_id=str(reversal_id),
            amount_minor=captured["amount"],
            fee_minor=captured["fee"],
            currency=captured["currency"],
            status=captured["status"],
            occurred_at=now.isoformat(),
        )
        return receipt, receipt.to_dict()


__all__ = [
    "MerchantRefundReceipt",
    "RefundMerchantPayment",
    "RefundMerchantPaymentCommand",
]
