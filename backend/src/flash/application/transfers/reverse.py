"""``CancelTransfer`` (BE-037) — annulation d'un transfert P2P par contre-passation.

Aucune ligne de ledger n'est modifiée ou supprimée : on ajoute une transaction
``REVERSAL`` qui inverse chaque posting de l'originale, puis on répercute sur les
projections de solde. Règles :
- seul l'émetteur peut annuler ;
- dans la fenêtre ``reversal_window`` (config, 1 h par défaut) → sinon
  ``ReversalWindowClosed`` ;
- une seule fois → sinon ``DuplicateOperation`` ;
- le destinataire doit encore disposer du montant reçu → sinon ``RefundNotPossible``.
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
from flash.domain.ledger.chart import Direction
from flash.domain.ledger.transaction import LedgerTransaction, TransactionKind
from flash.domain.shared.errors import (
    DuplicateOperation,
    InvalidInput,
    RefundNotPossible,
    ReversalWindowClosed,
)
from flash.domain.shared.identifiers import EntityId, IdempotencyKey
from flash.domain.wallet.events import TransferReversed


@dataclass(frozen=True, slots=True)
class CancelTransferCommand(Command):
    actor_user_id: str
    transfer_id: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class TransferReversalReceipt:
    reversal_id: str
    original_transfer_id: str
    reference: str
    amount_minor: int
    fee_minor: int
    currency: str
    sender_balance_after_minor: int
    occurred_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "reversal_id": self.reversal_id,
            "original_transfer_id": self.original_transfer_id,
            "reference": self.reference,
            "amount_minor": self.amount_minor,
            "fee_minor": self.fee_minor,
            "currency": self.currency,
            "sender_balance_after_minor": self.sender_balance_after_minor,
            "occurred_at": self.occurred_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TransferReversalReceipt:
        return cls(**{k: data[k] for k in cls.__dataclass_fields__})


class CancelTransfer(UseCase[CancelTransferCommand, TransferReversalReceipt]):
    def __init__(self, *, services: AppServices, window: timedelta) -> None:
        self._services = services
        self._window = window
        self._guard = IdempotencyGuard(services.idempotency)

    def execute(self, command: CancelTransferCommand) -> TransferReversalReceipt:
        try:
            key = IdempotencyKey(command.idempotency_key)
            transfer_id = EntityId(command.transfer_id)
        except ValueError as exc:
            raise InvalidInput(str(exc)) from exc

        outcome = self._guard.run(
            key=key,
            subject=command.actor_user_id,
            route="POST /v1/transfers/{id}/cancel",
            produce=lambda: self._reverse(command, transfer_id),
            rebuild=TransferReversalReceipt.from_dict,
        )
        return outcome.result

    def _reverse(
        self, command: CancelTransferCommand, transfer_id: EntityId
    ) -> tuple[TransferReversalReceipt, dict[str, Any]]:
        now = self._services.clock.now()
        reversal_id = self._services.ids.new_id()
        captured: dict[str, Any] = {}

        def work(uow: WorkUnitOfWork) -> None:
            original = uow.ledger.get(transfer_id)
            if original is None or original.kind is not TransactionKind.TRANSFER:
                raise InvalidInput("Transfert introuvable.")

            debit = next(p for p in original.postings if p.direction is Direction.DEBIT)
            recipient_credit = next(
                p
                for p in original.postings
                if p.direction is Direction.CREDIT and p.wallet_id is not None
            )
            assert debit.wallet_id is not None and recipient_credit.wallet_id is not None

            sender_wallet = uow.wallets.get_for_update(EntityId(str(debit.wallet_id)))
            if str(sender_wallet.user_id) != command.actor_user_id:
                # ne pas divulguer l'existence d'un transfert d'autrui
                raise InvalidInput("Transfert introuvable.")
            recipient_wallet = uow.wallets.get_for_update(EntityId(str(recipient_credit.wallet_id)))

            if now - original.occurred_at > self._window:
                raise ReversalWindowClosed()
            already = uow.ledger.get_by_reference(original.reference)
            if any(
                t.kind is TransactionKind.REVERSAL and t.reverses_transaction_id == original.id
                for t in already
            ):
                raise DuplicateOperation()

            amount = recipient_credit.amount
            total = debit.amount  # montant + frais
            fee = total - amount
            if recipient_wallet.available < amount:
                raise RefundNotPossible()

            uow.ledger.add(
                LedgerTransaction.reversal(
                    id=reversal_id,
                    original=original,
                    occurred_at=now,
                    reason="Annulation de transfert",
                )
            )
            recipient_wallet.debit(amount, now)
            sender_wallet.credit(total, now)
            uow.wallets.save(sender_wallet)
            uow.wallets.save(recipient_wallet)

            uow.add_event(
                TransferReversed(
                    occurred_at=now,
                    aggregate_id=str(reversal_id),
                    original_transfer_id=str(original.id),
                    sender_id=str(sender_wallet.user_id),
                    recipient_id=str(recipient_wallet.user_id),
                    amount_minor=amount.amount_minor,
                    fee_minor=fee.amount_minor,
                    currency=amount.currency.code,
                    reference=original.reference,
                )
            )
            captured.update(
                reference=original.reference,
                amount=amount.amount_minor,
                fee=fee.amount_minor,
                currency=amount.currency.code,
                sender_balance_after=sender_wallet.available.amount_minor,
            )

        execute_in_uow(self._services.uow, self._services.events, work)
        receipt = TransferReversalReceipt(
            reversal_id=str(reversal_id),
            original_transfer_id=str(transfer_id),
            reference=captured["reference"],
            amount_minor=captured["amount"],
            fee_minor=captured["fee"],
            currency=captured["currency"],
            sender_balance_after_minor=captured["sender_balance_after"],
            occurred_at=now.isoformat(),
        )
        return receipt, receipt.to_dict()


__all__ = ["CancelTransfer", "CancelTransferCommand", "TransferReversalReceipt"]
