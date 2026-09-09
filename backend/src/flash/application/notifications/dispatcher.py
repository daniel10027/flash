"""``NotificationDispatcher`` — traduit les événements de domaine en notifications.

Branché en aval de l'``EventPublisher`` (donc après commit) : la livraison est
best-effort et ne peut pas faire échouer une opération déjà validée.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from flash.application.notifications.model import Notification, NotificationKind
from flash.application.notifications.ports import Notifier
from flash.domain.card.events import (
    CardFrozen,
    CardPaymentAuthorized,
    CardPaymentDeclined,
    CardPaymentRefunded,
)
from flash.domain.cash.events import CashDepositCompleted, CashWithdrawalConfirmed
from flash.domain.identity.events import KycCaseApproved, KycCaseRejected
from flash.domain.merchants.events import MerchantPaymentCompleted, MerchantPaymentRefunded
from flash.domain.operators.events import (
    OperatorTransferFailed,
    OperatorTransferSucceeded,
)
from flash.domain.savings.events import (
    SavingsContributionSkipped,
    SavingsInterestCapitalised,
    SavingsPlanClosed,
    SavingsPlanFunded,
)
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


def _savings_funded(e: SavingsPlanFunded) -> list[_Spec]:
    if not e.scheduled:
        return []
    return [
        (
            e.user_id,
            NotificationKind.SAVINGS,
            "Versement d'épargne",
            f"{_money(e.amount_minor, e.currency)} versés sur « {e.plan_name} ».",
            {"plan_id": e.plan_id},
        )
    ]


def _savings_skipped(e: SavingsContributionSkipped) -> list[_Spec]:
    return [
        (
            e.user_id,
            NotificationKind.SAVINGS,
            "Versement d'épargne impossible",
            (
                f"Le versement de {_money(e.amount_minor, e.currency)} sur « {e.plan_name} » "
                "a été reporté (solde insuffisant)."
            ),
            {"plan_id": e.plan_id},
        )
    ]


def _savings_interest(e: SavingsInterestCapitalised) -> list[_Spec]:
    return [
        (
            e.user_id,
            NotificationKind.SAVINGS,
            "Intérêts d'épargne",
            f"{_money(e.amount_minor, e.currency)} d'intérêts ajoutés à « {e.plan_name} ».",
            {"plan_id": e.plan_id},
        )
    ]


def _savings_closed(e: SavingsPlanClosed) -> list[_Spec]:
    return [
        (
            e.user_id,
            NotificationKind.SAVINGS,
            "Plan d'épargne clôturé",
            f"« {e.plan_name} » a été clôturé, {_money(e.amount_minor, e.currency)} rapatriés.",
            {"plan_id": e.plan_id},
        )
    ]


def _operator_succeeded(e: OperatorTransferSucceeded) -> list[_Spec]:
    amount = _money(e.amount_minor, e.currency)
    ref = {"reference": e.reference, "operator": e.operator}
    if e.direction == "PAYOUT":
        title, body = "Envoi opérateur effectué", f"{amount} envoyés vers {e.msisdn_masked}."
    else:
        net = _money(e.amount_minor - e.fee_minor, e.currency)
        title, body = "Rechargement reçu", f"{net} crédités depuis {e.msisdn_masked}."
    return [(e.user_id, NotificationKind.OPERATOR, title, body, ref)]


def _operator_failed(e: OperatorTransferFailed) -> list[_Spec]:
    amount = _money(e.amount_minor, e.currency)
    verb = "L'envoi" if e.direction == "PAYOUT" else "Le rechargement"
    return [
        (
            e.user_id,
            NotificationKind.OPERATOR,
            "Opération opérateur échouée",
            f"{verb} de {amount} a échoué ({e.reason}). Les fonds réservés sont rendus.",
            {"reference": e.reference},
        )
    ]


def _card_authorized(e: CardPaymentAuthorized) -> list[_Spec]:
    where = f" chez {e.merchant_name}" if e.merchant_name else ""
    return [
        (
            e.user_id,
            NotificationKind.CARD,
            "Paiement carte",
            f"Autorisation de {_money(e.amount_minor, e.currency)}{where}.",
            {"authorization_id": e.authorization_id},
        )
    ]


def _card_declined(e: CardPaymentDeclined) -> list[_Spec]:
    return [
        (
            e.user_id,
            NotificationKind.CARD,
            "Paiement carte refusé",
            f"Un paiement de {_money(e.amount_minor, e.currency)} a été refusé ({e.reason}).",
            {"authorization_id": e.authorization_id, "reason": e.reason},
        )
    ]


def _card_frozen(e: CardFrozen) -> list[_Spec]:
    return [
        (
            e.user_id,
            NotificationKind.CARD,
            "Carte gelée",
            f"Votre carte a été gelée : {e.reason}",
            {"card_id": e.card_id},
        )
    ]


def _card_refunded(e: CardPaymentRefunded) -> list[_Spec]:
    return [
        (
            e.user_id,
            NotificationKind.CARD,
            "Remboursement carte",
            f"{_money(e.amount_minor, e.currency)} vous ont été remboursés sur votre carte.",
            {"authorization_id": e.authorization_id},
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
    SavingsPlanFunded: _savings_funded,
    SavingsContributionSkipped: _savings_skipped,
    SavingsInterestCapitalised: _savings_interest,
    SavingsPlanClosed: _savings_closed,
    CardPaymentAuthorized: _card_authorized,
    CardPaymentDeclined: _card_declined,
    CardFrozen: _card_frozen,
    CardPaymentRefunded: _card_refunded,
    OperatorTransferSucceeded: _operator_succeeded,
    OperatorTransferFailed: _operator_failed,
}


__all__ = ["NotificationDispatcher"]
