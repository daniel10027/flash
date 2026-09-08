"""Types d'opérations monétaires — référencés par la tarification et les limites."""

from __future__ import annotations

from enum import StrEnum


class OperationType(StrEnum):
    """Opération soumise à tarification et/ou plafonds."""

    TRANSFER = "TRANSFER"  # transfert P2P entre comptes Flash
    MERCHANT_PAYMENT = "MERCHANT_PAYMENT"  # paiement à un marchand par QR
    CASH_DEPOSIT = "CASH_DEPOSIT"  # dépôt d'espèces chez un agent
    CASH_WITHDRAWAL = "CASH_WITHDRAWAL"  # retrait d'espèces chez un agent
    OPERATOR_PAYOUT = "OPERATOR_PAYOUT"  # envoi vers un compte opérateur (Orange/MTN/Moov)
    OPERATOR_COLLECT = "OPERATOR_COLLECT"  # rechargement depuis un compte opérateur
    BILL_PAYMENT = "BILL_PAYMENT"  # paiement de facture (eau, électricité, TV…)
    AIRTIME_PURCHASE = "AIRTIME_PURCHASE"  # achat de crédit / forfait


__all__ = ["OperationType"]
