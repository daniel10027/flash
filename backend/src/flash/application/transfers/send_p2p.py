"""Cas d'usage ``SendP2PTransfer`` (BE-031) — transfert d'argent entre comptes Flash.

Flux (cf. ``docs/architecture.md`` §3) :
1. idempotence (clé cloisonnée par émetteur + route) ;
2. résolution émetteur / destinataire / portefeuilles (verrou pessimiste) ;
3. frais = ``PricingService`` (0,8 % en CI), contrôle KYC + plafonds + plafond de solde
   du destinataire ;
4. ``LedgerTransaction.transfer`` (débit émetteur ``montant + frais``, crédit
   destinataire ``montant``, crédit produits ``frais``) — équilibrée par construction ;
5. mise à jour des projections de solde, événement ``TransferCompleted``, reçu.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from flash.application.idempotency import IdempotencyGuard
from flash.application.services import AppServices
from flash.application.transaction import execute_in_uow
from flash.application.unit_of_work import WorkUnitOfWork
from flash.application.use_case import Command, UseCase
from flash.domain.identity.user import User
from flash.domain.ledger.chart import AccountType
from flash.domain.ledger.transaction import LedgerTransaction
from flash.domain.limits.limits import KycPolicy, LimitPolicy
from flash.domain.pricing.pricing import PricingService
from flash.domain.shared.errors import InvalidInput, RecipientNotFound, SelfTransfer
from flash.domain.shared.identifiers import CountryCode, EntityId, IdempotencyKey, Msisdn
from flash.domain.shared.money import Money
from flash.domain.shared.operations import OperationType
from flash.domain.wallet.events import TransferCompleted

_ROUTE = "POST /v1/transfers"
_OP = OperationType.TRANSFER


@dataclass(frozen=True, slots=True)
class SendP2PTransferCommand(Command):
    sender_user_id: str
    recipient_phone_number: str
    amount_minor: int
    idempotency_key: str
    country: str | None = None
    note: str | None = None


@dataclass(frozen=True, slots=True)
class TransferReceipt:
    transfer_id: str
    reference: str
    amount_minor: int
    fee_minor: int
    total_minor: int
    currency: str
    recipient_masked: str
    sender_balance_after_minor: int
    occurred_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "transfer_id": self.transfer_id,
            "reference": self.reference,
            "amount_minor": self.amount_minor,
            "fee_minor": self.fee_minor,
            "total_minor": self.total_minor,
            "currency": self.currency,
            "recipient_masked": self.recipient_masked,
            "sender_balance_after_minor": self.sender_balance_after_minor,
            "occurred_at": self.occurred_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TransferReceipt:
        return cls(**{k: data[k] for k in cls.__dataclass_fields__})


class SendP2PTransfer(UseCase[SendP2PTransferCommand, TransferReceipt]):
    def __init__(
        self,
        *,
        services: AppServices,
        pricing: PricingService,
        limits: LimitPolicy,
        kyc: KycPolicy,
    ) -> None:
        self._services = services
        self._pricing = pricing
        self._limits = limits
        self._kyc = kyc
        self._guard = IdempotencyGuard(services.idempotency)

    def execute(self, command: SendP2PTransferCommand) -> TransferReceipt:
        if command.amount_minor <= 0:
            raise InvalidInput("Le montant doit être strictement positif.")
        try:
            default_cc = CountryCode(command.country.upper()) if command.country else None
            recipient_msisdn = Msisdn.parse(
                command.recipient_phone_number, default_country=default_cc
            )
            key = IdempotencyKey(command.idempotency_key)
        except ValueError as exc:
            raise InvalidInput(str(exc)) from exc

        outcome = self._guard.run(
            key=key,
            subject=command.sender_user_id,
            route=_ROUTE,
            produce=lambda: self._transfer(command, recipient_msisdn),
            rebuild=TransferReceipt.from_dict,
        )
        return outcome.result

    def _transfer(
        self, command: SendP2PTransferCommand, recipient_msisdn: Msisdn
    ) -> tuple[TransferReceipt, dict[str, Any]]:
        now = self._services.clock.now()
        txn_id = self._services.ids.new_id()
        reference = f"TRX-{txn_id}"
        captured: dict[str, Any] = {}

        def work(uow: WorkUnitOfWork) -> None:
            sender: User | None = uow.users.get(EntityId(command.sender_user_id))
            if sender is None:  # pragma: no cover - jeton valide
                raise InvalidInput("Compte émetteur introuvable.")
            sender.ensure_can_transact()

            recipient: User | None = uow.users.get_by_msisdn(recipient_msisdn)
            if recipient is None:
                raise RecipientNotFound(msisdn=recipient_msisdn.masked())
            if recipient.id == sender.id:
                raise SelfTransfer()

            sender_wallet = uow.wallets.get_for_update(_primary_wallet_id(uow, sender.id))
            currency = sender_wallet.currency
            amount = Money(command.amount_minor, currency)

            recipient_wallet = uow.wallets.get_for_user(recipient.id, currency)
            if recipient_wallet is None:
                raise RecipientNotFound(msisdn=recipient_msisdn.masked())
            recipient_wallet = uow.wallets.get_for_update(recipient_wallet.id)

            fee = self._pricing.fee_for(country=sender.country, operation=_OP, amount=amount).total
            self._kyc.require(operation=_OP, kyc_tier=sender.kyc_tier)
            self._limits.check(
                user_id=sender.id,
                country=sender.country,
                kyc_tier=sender.kyc_tier,
                operation=_OP,
                amount=amount,
            )
            self._limits.check_balance_cap(
                country=recipient.country,
                kyc_tier=recipient.kyc_tier,
                operation=_OP,
                current_balance=recipient_wallet.balance,
                incoming=amount,
            )

            sender_account = uow.ledger.ensure_account(
                account_type=AccountType.CLIENT_LIABILITY,
                currency=currency,
                owner_ref=str(sender.id),
            )
            recipient_account = uow.ledger.ensure_account(
                account_type=AccountType.CLIENT_LIABILITY,
                currency=currency,
                owner_ref=str(recipient.id),
            )
            fee_account = uow.ledger.ensure_account(
                account_type=AccountType.FLASH_FEE_INCOME, currency=currency
            )

            txn = LedgerTransaction.transfer(
                id=txn_id,
                occurred_at=now,
                reference=reference,
                sender_account_id=sender_account,
                sender_wallet_id=sender_wallet.id,
                recipient_account_id=recipient_account,
                recipient_wallet_id=recipient_wallet.id,
                fee_income_account_id=fee_account,
                amount=amount,
                fee=fee,
                metadata={"note": command.note} if command.note else {},
            )
            uow.ledger.add(txn)

            sender_wallet.debit(amount + fee, now)  # lève InsufficientFunds si besoin
            recipient_wallet.credit(amount, now)
            uow.wallets.save(sender_wallet)
            uow.wallets.save(recipient_wallet)

            uow.add_event(
                TransferCompleted(
                    occurred_at=now,
                    aggregate_id=str(txn_id),
                    sender_id=str(sender.id),
                    recipient_id=str(recipient.id),
                    amount_minor=amount.amount_minor,
                    fee_minor=fee.amount_minor,
                    currency=currency.code,
                    reference=reference,
                )
            )
            captured.update(
                amount=amount.amount_minor,
                fee=fee.amount_minor,
                currency=currency.code,
                sender_balance_after=sender_wallet.available.amount_minor,
            )

        execute_in_uow(self._services.uow, self._services.events, work)

        receipt = TransferReceipt(
            transfer_id=str(txn_id),
            reference=reference,
            amount_minor=captured["amount"],
            fee_minor=captured["fee"],
            total_minor=captured["amount"] + captured["fee"],
            currency=captured["currency"],
            recipient_masked=recipient_msisdn.masked(),
            sender_balance_after_minor=captured["sender_balance_after"],
            occurred_at=_iso(now),
        )
        return receipt, receipt.to_dict()


def _primary_wallet_id(uow: Any, user_id: EntityId) -> EntityId:
    wallets = uow.wallets.list_for_user(user_id)
    if not wallets:  # pragma: no cover - un compte a toujours son wallet
        raise InvalidInput("Aucun portefeuille pour l'émetteur.")
    return EntityId(str(wallets[0].id))


def _iso(moment: datetime) -> str:
    return moment.isoformat()


__all__ = ["SendP2PTransfer", "SendP2PTransferCommand", "TransferReceipt"]
