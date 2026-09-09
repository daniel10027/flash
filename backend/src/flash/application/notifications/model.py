"""Modèle d'une notification livrée à un utilisateur."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import StrEnum
from typing import Any


class NotificationKind(StrEnum):
    MONEY_IN = "MONEY_IN"  # de l'argent est arrivé
    MONEY_OUT = "MONEY_OUT"  # un débit a eu lieu
    CASH_DEPOSIT = "CASH_DEPOSIT"  # dépôt cash en agence
    CASH_WITHDRAWAL = "CASH_WITHDRAWAL"  # retrait cash en agence
    MERCHANT_PAYMENT = "MERCHANT_PAYMENT"  # paiement à un marchand
    REVERSAL = "REVERSAL"  # annulation / remboursement
    KYC = "KYC"  # avancement de la vérification d'identité
    VAULT = "VAULT"  # mouvement de coffre (mise de côté / reprise)
    SAVINGS = "SAVINGS"  # épargne : versement programmé, intérêts, clôture
    CARD = "CARD"  # carte : autorisation, refus, gel, remboursement
    OPERATOR = "OPERATOR"  # interop opérateur mobile money (envoi / rechargement)
    SECURITY = "SECURITY"  # événement de sécurité (nouvel appareil…)


@dataclass(frozen=True, slots=True)
class Notification:
    id: str
    user_id: str
    kind: NotificationKind
    title: str
    body: str
    created_at: datetime
    data: dict[str, Any] = field(default_factory=dict)
    read_at: datetime | None = None

    @property
    def is_read(self) -> bool:
        return self.read_at is not None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "kind": self.kind.value,
            "title": self.title,
            "body": self.body,
            "data": self.data,
            "created_at": self.created_at.isoformat(),
            "read_at": self.read_at.isoformat() if self.read_at else None,
        }


__all__ = ["Notification", "NotificationKind"]
