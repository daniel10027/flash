"""``NotificationDispatcher`` — traduit les événements de domaine en notifications.

Branché en aval de l'``EventPublisher`` (donc après commit) : la livraison est
best-effort et ne peut pas faire échouer une opération déjà validée.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from flash.application.notifications.model import Notification, NotificationKind
from flash.application.notifications.ports import Notifier
from flash.domain.cash.events import CashDepositCompleted, CashWithdrawalConfirmed
from flash.domain.identity.events import KycCaseApproved, KycCaseRejected
from flash.domain.merchants.events import MerchantPaymentCompleted, MerchantPaymentRefunded
from flash.domain.shared.events import DomainEvent
from flash.domain.shared.ports import Clock, IdGenerator
from flash.domain.vault.events import VaultPocketDeposited, VaultPocketWithdrawn
from flash.domain.wallet.events import TransferCompleted, TransferReversed


def _money(minor: int, currency: str) -> str:
    return f"{minor:,}".replace(",", " ") + f" {currency}"


class NotificationDispatcher:
    def __init__(self, *, notifier: Notifier, clock: Clock, ids: IdGenerator) -> None:
        self._notifier = notifier
        self._clock = clock
        self._ids = ids

    def handle(self, events: Iterable[DomainEvent]) -> None:
        for event in events:
            for note in self._notifications_for(event):
                self._notifier.deliver(note)

    # ------------------------------------------------------------------ mapping
    def _notifications_for(self, event: DomainEvent) -> list[Notification]:
        builder = _BUILDERS.get(type(event))
        if builder is None:
            return []
        specs = builder(event)
        now = self._clock.now()
        return [
            Notification(
                id=str(self._ids.new_id()),
                user_id=user_id,
                kind=kind,
                title=title,
                body=body,
                created_at=now,
                data=data,
            )
            for (user_id, kind, title, body, data) in specs
        ]


_Spec = tuple[str, NotificationKind, str, str, dict[str, Any]]


def _transfer_completed(e: TransferCompleted) -> list[_Spec]:
    amount = _money(e.amount_minor, e.currency)
    total = _money(e.amount_minor + e.fee_minor, e.currency)
    ref = {"reference": e.reference}
    return [
        (
            e.recipient_id,
            NotificationKind.MONEY_IN,
            "Argent reçu",
            f"Vous avez reçu {amount}.",
            ref,
        ),
        (
            e.sender_id,
            NotificationKind.MONEY_OUT,
            "Transfert envoyé",
            f"Vous avez envoyé {amount} ({total} avec les frais).",
            ref,
        ),
    ]


def _transfer_reversed(e: TransferReversed) -> list[_Spec]:
    amount = _money(e.amount_minor, e.currency)
    ref = {"reference": e.reference}
    return [
        (
            e.sender_id,
            NotificationKind.REVERSAL,
            "Transfert annulé",
            f"Votre transfert de {amount} a été annulé et recrédité.",
            ref,
        ),
        (
            e.recipient_id,
            NotificationKind.REVERSAL,
            "Transfert repris",
            f"Un transfert de {amount} reçu a été annulé.",
            ref,
        ),
    ]


def _cash_deposit(e: CashDepositCompleted) -> list[_Spec]:
    return [
        (
            e.client_id,
            NotificationKind.CASH_DEPOSIT,
            "Dépôt reçu",
            f"Un dépôt de {_money(e.amount_minor, e.currency)} a été crédité sur votre compte.",
            {},
        )
    ]


def _cash_withdrawal(e: CashWithdrawalConfirmed) -> list[_Spec]:
    return [
        (
            e.client_id,
            NotificationKind.CASH_WITHDRAWAL,
            "Retrait effectué",
            f"Un retrait de {_money(e.amount_minor, e.currency)} a été confirmé.",
            {},
        )
    ]


def _merchant_payment(e: MerchantPaymentCompleted) -> list[_Spec]:
    return [
        (
            e.payer_id,
            NotificationKind.MERCHANT_PAYMENT,
            "Paiement effectué",
            f"Vous avez payé {_money(e.amount_minor, e.currency)} à un marchand.",
            {"reference": e.reference},
        )
    ]


def _merchant_refund(e: MerchantPaymentRefunded) -> list[_Spec]:
    return [
        (
            e.payer_id,
            NotificationKind.REVERSAL,
            "Paiement remboursé",
            f"Un paiement marchand de {_money(e.amount_minor, e.currency)} vous a été remboursé.",
            {"reference": e.reference},
        )
    ]


def _vault_deposited(e: VaultPocketDeposited) -> list[_Spec]:
    return [
        (
            e.user_id,
            NotificationKind.VAULT,
            "Mis de côté",
            f"{_money(e.amount_minor, e.currency)} placés dans « {e.pocket_name} ».",
            {"pocket_id": e.pocket_id},
        )
    ]


def _vault_withdrawn(e: VaultPocketWithdrawn) -> list[_Spec]:
    return [
        (
            e.user_id,
            NotificationKind.VAULT,
            "Repris du coffre",
            f"{_money(e.amount_minor, e.currency)} repris de « {e.pocket_name} ».",
            {"pocket_id": e.pocket_id},
        )
    ]


def _kyc_approved(e: KycCaseApproved) -> list[_Spec]:
    return [
        (
            e.user_id,
            NotificationKind.KYC,
            "Identité vérifiée",
            f"Votre compte est passé au palier de vérification {e.target_tier}.",
            {"target_tier": e.target_tier},
        )
    ]


def _kyc_rejected(e: KycCaseRejected) -> list[_Spec]:
    return [
        (
            e.user_id,
            NotificationKind.KYC,
            "Vérification refusée",
            f"Votre dossier a été refusé : {e.reason}",
            {},
        )
    ]


_BUILDERS: dict[type[DomainEvent], Callable[[Any], list[_Spec]]] = {
    TransferCompleted: _transfer_completed,
    TransferReversed: _transfer_reversed,
    CashDepositCompleted: _cash_deposit,
    CashWithdrawalConfirmed: _cash_withdrawal,
    MerchantPaymentCompleted: _merchant_payment,
    MerchantPaymentRefunded: _merchant_refund,
    KycCaseApproved: _kyc_approved,
    KycCaseRejected: _kyc_rejected,
    VaultPocketDeposited: _vault_deposited,
    VaultPocketWithdrawn: _vault_withdrawn,
}


__all__ = ["NotificationDispatcher"]
