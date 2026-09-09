"""Résolution des transferts opérateurs sur webhook (BE-067).

Idempotent : un ``reference`` déjà résolu renvoie simplement son statut. Sur ``SUCCEEDED``
l'écriture ledger équilibrée est posée et le portefeuille est mis à jour ; sur ``FAILED``
la réserve d'un ``PAYOUT`` est rendue (le ``COLLECT`` n'avait rien réservé).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flash.application.services import AppServices
from flash.application.transaction import execute_in_uow
from flash.application.unit_of_work import WorkUnitOfWork
from flash.application.use_case import Command, UseCase
from flash.domain.ledger.chart import AccountType
from flash.domain.ledger.transaction import LedgerTransaction
from flash.domain.operators.transfer import OperatorTransfer, OperatorTransferDirection
from flash.domain.shared.errors import InvalidInput
from flash.domain.shared.identifiers import EntityId

_SUCCEEDED = "SUCCEEDED"
_FAILED = "FAILED"


@dataclass(frozen=True, slots=True)
class OperatorCallbackCommand(Command):
    operator: str
    reference: str
    status: str
    external_ref: str | None = None
    reason: str | None = None


@dataclass(frozen=True, slots=True)
class OperatorCallbackResult:
    reference: str
    status: str
    applied: bool

    def to_dict(self) -> dict[str, Any]:
        return {"reference": self.reference, "status": self.status, "applied": self.applied}


class HandleOperatorCallback(UseCase[OperatorCallbackCommand, OperatorCallbackResult]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: OperatorCallbackCommand) -> OperatorCallbackResult:
        status = command.status.upper()
        if status not in (_SUCCEEDED, _FAILED):
            raise InvalidInput("Statut de callback inconnu (SUCCEEDED / FAILED attendu).")
        now = self._services.clock.now()
        txn_id = self._services.ids.new_id()
        captured: dict[str, Any] = {}

        def work(uow: WorkUnitOfWork) -> None:
            try:
                transfer = uow.operator_transfers.get_for_update_by_reference(command.reference)
            except KeyError as exc:
                raise InvalidInput("Transfert opérateur introuvable.") from exc
            if transfer.operator != command.operator:
                raise InvalidInput("Cet opérateur n'est pas l'émetteur de ce transfert.")

            if not transfer.is_pending:  # rejeu : rien à faire
                captured.update(status=transfer.status.value, applied=False)
                return

            if status == _FAILED:
                self._fail(uow, transfer, command.reason or "Échec opérateur", now)
            else:
                self._succeed(uow, transfer, command.external_ref, txn_id, now)
            uow.operator_transfers.save(transfer)
            captured.update(status=transfer.status.value, applied=True)

        execute_in_uow(self._services.uow, self._services.events, work)
        return OperatorCallbackResult(
            reference=command.reference, status=captured["status"], applied=captured["applied"]
        )

    def _fail(
        self, uow: WorkUnitOfWork, transfer: OperatorTransfer, reason: str, now: Any
    ) -> None:
        if transfer.direction is OperatorTransferDirection.PAYOUT:
            wallet = uow.wallets.get_for_update(EntityId(str(transfer.wallet_id)))
            wallet.release(transfer.debit_total, now)
            uow.wallets.save(wallet)
        transfer.mark_failed(reason=reason, now=now)

    def _succeed(
        self,
        uow: WorkUnitOfWork,
        transfer: OperatorTransfer,
        external_ref: str | None,
        txn_id: EntityId,
        now: Any,
    ) -> None:
        wallet = uow.wallets.get_for_update(EntityId(str(transfer.wallet_id)))
        client_acc = uow.ledger.ensure_account(
            account_type=AccountType.CLIENT_LIABILITY,
            currency=wallet.currency,
            owner_ref=str(wallet.user_id),
        )
        suspense_acc = uow.ledger.ensure_account(
            account_type=AccountType.OPERATOR_SUSPENSE, currency=wallet.currency
        )
        fee_acc = uow.ledger.ensure_account(
            account_type=AccountType.FLASH_FEE_INCOME, currency=wallet.currency
        )
        meta = {
            "operator": transfer.operator,
            "msisdn_masked": transfer.msisdn.masked(),
            "fee_minor": transfer.fee.amount_minor,
        }
        if transfer.direction is OperatorTransferDirection.PAYOUT:
            meta["amount_minor"] = transfer.amount.amount_minor
            uow.ledger.add(
                LedgerTransaction.operator_payout(
                    id=txn_id,
                    occurred_at=now,
                    reference=transfer.reference,
                    client_account_id=client_acc,
                    client_wallet_id=EntityId(str(wallet.id)),
                    operator_suspense_account_id=suspense_acc,
                    fee_income_account_id=fee_acc,
                    amount=transfer.amount,
                    fee=transfer.fee,
                    metadata=meta,
                )
            )
            wallet.settle_reservation(transfer.debit_total, now)
        else:
            meta["amount_minor"] = transfer.credit_net.amount_minor
            uow.ledger.add(
                LedgerTransaction.operator_collect(
                    id=txn_id,
                    occurred_at=now,
                    reference=transfer.reference,
                    operator_suspense_account_id=suspense_acc,
                    client_account_id=client_acc,
                    client_wallet_id=EntityId(str(wallet.id)),
                    fee_income_account_id=fee_acc,
                    amount=transfer.amount,
                    fee=transfer.fee,
                    metadata=meta,
                )
            )
            wallet.credit(transfer.credit_net, now)
        uow.wallets.save(wallet)
        transfer.mark_succeeded(
            external_ref=external_ref, ledger_transaction_id=txn_id, now=now
        )


__all__ = ["HandleOperatorCallback", "OperatorCallbackCommand", "OperatorCallbackResult"]
