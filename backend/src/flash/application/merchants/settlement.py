"""Règlements marchands (BE-070) : configuration, déclenchement manuel, relevé.

Un règlement solde le net accumulé (``amount - fee``) des ``MerchantPayment``
``COMPLETED`` non encore réglés, par un virement bancaire (port ``BankGateway``) doublé
d'une écriture ``MERCHANT_PAYABLE`` → ``BANK_SETTLEMENT``. Le job
``application/jobs/merchant_settle.py`` applique la même logique en boucle sur les
marchands échus.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flash.application.merchants.bank import BankGateway
from flash.application.merchants.operations import NotAMerchant
from flash.application.services import AppServices
from flash.application.transaction import execute_in_uow
from flash.application.unit_of_work import WorkUnitOfWork
from flash.application.use_case import Command, UseCase
from flash.domain.ledger.chart import AccountType
from flash.domain.ledger.transaction import LedgerTransaction
from flash.domain.merchants.bank_account import BankAccount
from flash.domain.merchants.merchant import Merchant, SettlementFrequency
from flash.domain.merchants.settlement import MerchantSettlement
from flash.domain.shared.errors import InvalidInput
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import Money
from flash.domain.shared.ports import Clock, IdGenerator


@dataclass(frozen=True, slots=True)
class SettlementView:
    settlement_id: str
    merchant_id: str
    amount_minor: int
    currency: str
    payment_count: int
    status: str
    bank_reference: str | None
    failure_reason: str | None
    created_at: str
    settled_at: str | None

    @classmethod
    def of(cls, settlement: MerchantSettlement) -> SettlementView:
        return cls(
            settlement_id=str(settlement.id),
            merchant_id=str(settlement.merchant_id),
            amount_minor=settlement.amount.amount_minor,
            currency=settlement.currency_code,
            payment_count=settlement.payment_count,
            status=settlement.status.value,
            bank_reference=settlement.bank_reference,
            failure_reason=settlement.failure_reason,
            created_at=settlement.created_at.isoformat(),
            settled_at=settlement.settled_at.isoformat() if settlement.settled_at else None,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "settlement_id": self.settlement_id,
            "merchant_id": self.merchant_id,
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "payment_count": self.payment_count,
            "status": self.status,
            "bank_reference": self.bank_reference,
            "failure_reason": self.failure_reason,
            "created_at": self.created_at,
            "settled_at": self.settled_at,
        }


@dataclass(frozen=True, slots=True)
class SettlementLineView:
    payment_id: str
    reference: str
    gross_minor: int
    fee_minor: int
    net_minor: int
    currency: str
    occurred_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "payment_id": self.payment_id,
            "reference": self.reference,
            "gross_minor": self.gross_minor,
            "fee_minor": self.fee_minor,
            "net_minor": self.net_minor,
            "currency": self.currency,
            "occurred_at": self.occurred_at,
        }


# ---------------------------------------------------------------- exécution partagée
def settle_merchant(
    uow: WorkUnitOfWork,
    merchant: Merchant,
    *,
    bank: BankGateway,
    ids: IdGenerator,
    clock: Clock,
) -> MerchantSettlement | None:
    """Règle le net accumulé du marchand. ``None`` s'il n'y a rien à régler."""
    account = merchant.require_bank_account()
    now = clock.now()
    pending = uow.merchant_payments.list_settleable(merchant.id)
    if not pending:
        merchant.advance_settlement_schedule(now)
        uow.merchants.save(merchant)
        return None

    total = Money.zero(merchant.currency)
    for payment in pending:
        total = total + payment.net_to_merchant

    settlement_id = ids.new_id()
    settlement = MerchantSettlement.open(
        settlement_id=settlement_id,
        merchant_id=merchant.id,
        user_id=merchant.user_id,
        amount=total,
        payment_count=len(pending),
        now=now,
    )
    uow.merchant_settlements.add(settlement)

    ack = bank.transfer(
        holder=account.holder,
        iban=account.iban,
        bank_name=account.bank_name,
        amount_minor=total.amount_minor,
        currency=merchant.currency.code,
        reference=f"MSET-{settlement_id}",
    )
    if not ack.accepted:
        settlement.mark_failed(reason=ack.reason or "Virement refusé.", now=now)
        uow.merchant_settlements.save(settlement)
        merchant.advance_settlement_schedule(now)
        uow.merchants.save(merchant)
        return settlement

    payable_acc = uow.ledger.ensure_account(
        account_type=AccountType.MERCHANT_PAYABLE,
        currency=merchant.currency,
        owner_ref=str(merchant.id),
    )
    bank_acc = uow.ledger.ensure_account(
        account_type=AccountType.BANK_SETTLEMENT, currency=merchant.currency
    )
    txn_id = ids.new_id()
    uow.ledger.add(
        LedgerTransaction.merchant_settlement(
            id=txn_id,
            occurred_at=now,
            reference=f"MSET-{settlement_id}",
            merchant_payable_account_id=payable_acc,
            bank_settlement_account_id=bank_acc,
            amount=total,
            metadata={
                "merchant_name": merchant.display_name,
                "payment_count": len(pending),
                "bank_iban_masked": account.masked(),
            },
        )
    )
    for payment in pending:
        payment.attach_settlement(settlement_id)
        uow.merchant_payments.save(payment)
    settlement.mark_paid(bank_reference=ack.bank_reference, ledger_transaction_id=txn_id, now=now)
    uow.merchant_settlements.save(settlement)
    merchant.record_settlement(settlement_id=settlement_id, now=now)
    uow.merchants.save(merchant)
    return settlement


# ============================================================== configuration
@dataclass(frozen=True, slots=True)
class ConfigureMerchantSettlementCommand(Command):
    merchant_user_id: str
    holder: str
    iban: str
    bank_name: str
    frequency: str = "MANUAL"


@dataclass(frozen=True, slots=True)
class MerchantSettlementConfigView:
    frequency: str
    bank_iban_masked: str
    bank_name: str
    next_settlement_at: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "frequency": self.frequency,
            "bank_iban_masked": self.bank_iban_masked,
            "bank_name": self.bank_name,
            "next_settlement_at": self.next_settlement_at,
        }


class ConfigureMerchantSettlement(
    UseCase[ConfigureMerchantSettlementCommand, MerchantSettlementConfigView]
):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(
        self, command: ConfigureMerchantSettlementCommand
    ) -> MerchantSettlementConfigView:
        try:
            frequency = SettlementFrequency(command.frequency)
        except ValueError as exc:
            raise InvalidInput("Fréquence de règlement inconnue.") from exc
        try:
            account = BankAccount(
                holder=command.holder, iban=command.iban, bank_name=command.bank_name
            )
        except ValueError as exc:
            raise InvalidInput(str(exc)) from exc
        now = self._services.clock.now()
        captured: list[MerchantSettlementConfigView] = []

        def work(uow: WorkUnitOfWork) -> None:
            merchant = uow.merchants.get_by_user_id(EntityId(command.merchant_user_id))
            if merchant is None:
                raise NotAMerchant()
            merchant.ensure_active()
            merchant.configure_settlement(bank_account=account, frequency=frequency, now=now)
            uow.merchants.save(merchant)
            captured.append(
                MerchantSettlementConfigView(
                    frequency=frequency.value,
                    bank_iban_masked=account.masked(),
                    bank_name=account.bank_name,
                    next_settlement_at=(
                        merchant.next_settlement_at.isoformat()
                        if merchant.next_settlement_at
                        else None
                    ),
                )
            )

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


# ============================================================== déclenchement manuel
@dataclass(frozen=True, slots=True)
class SettleMerchantNowCommand(Command):
    merchant_user_id: str


class SettleMerchantNow(UseCase[SettleMerchantNowCommand, SettlementView | None]):
    def __init__(self, *, services: AppServices, bank: BankGateway) -> None:
        self._services = services
        self._bank = bank

    def execute(self, command: SettleMerchantNowCommand) -> SettlementView | None:
        captured: list[SettlementView] = []

        def work(uow: WorkUnitOfWork) -> None:
            merchant = uow.merchants.get_by_user_id(EntityId(command.merchant_user_id))
            if merchant is None:
                raise NotAMerchant()
            merchant.ensure_active()
            settlement = settle_merchant(
                uow,
                merchant,
                bank=self._bank,
                ids=self._services.ids,
                clock=self._services.clock,
            )
            if settlement is not None:
                captured.append(SettlementView.of(settlement))

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0] if captured else None


# ============================================================== lectures
@dataclass(frozen=True, slots=True)
class ListMerchantSettlementsCommand(Command):
    merchant_user_id: str


class ListMerchantSettlements(
    UseCase[ListMerchantSettlementsCommand, list[SettlementView]]
):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(
        self, command: ListMerchantSettlementsCommand
    ) -> list[SettlementView]:
        with self._services.uow() as uow:
            merchant = uow.merchants.get_by_user_id(EntityId(command.merchant_user_id))
            if merchant is None:
                raise NotAMerchant()
            return [
                SettlementView.of(s)
                for s in uow.merchant_settlements.list_for_merchant(merchant.id)
            ]


@dataclass(frozen=True, slots=True)
class GetSettlementStatementCommand(Command):
    merchant_user_id: str
    settlement_id: str


@dataclass(frozen=True, slots=True)
class SettlementStatement:
    settlement: SettlementView
    lines: list[SettlementLineView]

    def to_dict(self) -> dict[str, Any]:
        return {
            "settlement": self.settlement.to_dict(),
            "lines": [line.to_dict() for line in self.lines],
        }


class GetSettlementStatement(
    UseCase[GetSettlementStatementCommand, SettlementStatement]
):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: GetSettlementStatementCommand) -> SettlementStatement:
        with self._services.uow() as uow:
            merchant = uow.merchants.get_by_user_id(EntityId(command.merchant_user_id))
            if merchant is None:
                raise NotAMerchant()
            try:
                settlement = uow.merchant_settlements.get(EntityId(command.settlement_id))
            except ValueError as exc:
                raise InvalidInput("Règlement introuvable.") from exc
            if settlement is None or settlement.merchant_id != merchant.id:
                raise InvalidInput("Règlement introuvable.")
            lines = [
                SettlementLineView(
                    payment_id=str(p.id),
                    reference=p.reference,
                    gross_minor=p.amount.amount_minor,
                    fee_minor=p.fee.amount_minor,
                    net_minor=p.net_to_merchant.amount_minor,
                    currency=p.currency_code,
                    occurred_at=p.created_at.isoformat(),
                )
                for p in uow.merchant_payments.list_for_settlement(settlement.id)
            ]
            return SettlementStatement(settlement=SettlementView.of(settlement), lines=lines)


__all__ = [
    "ConfigureMerchantSettlement",
    "ConfigureMerchantSettlementCommand",
    "GetSettlementStatement",
    "GetSettlementStatementCommand",
    "ListMerchantSettlements",
    "ListMerchantSettlementsCommand",
    "MerchantSettlementConfigView",
    "SettleMerchantNow",
    "SettleMerchantNowCommand",
    "SettlementLineView",
    "SettlementStatement",
    "SettlementView",
    "settle_merchant",
]
