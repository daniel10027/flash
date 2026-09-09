"""Job de réconciliation (BE-045) — compare la projection de solde de chaque
portefeuille (``available + reserved + vaulted``) au solde recalculé depuis le ledger.

Lecture seule : le job **signale** les écarts (retour + journal), il ne corrige rien
automatiquement (un écart est un incident à investiguer, pas une donnée à réécrire).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flash.application.services import AppServices
from flash.domain.shared.identifiers import EntityId

_PAGE = 500


@dataclass(frozen=True, slots=True)
class WalletDiscrepancy:
    wallet_id: str
    user_id: str
    currency: str
    projected_minor: int  # available + reserved + vaulted (projection wallets)
    ledger_minor: int  # recalculé depuis les postings
    delta_minor: int  # projected - ledger

    def to_dict(self) -> dict[str, Any]:
        return {
            "wallet_id": self.wallet_id,
            "user_id": self.user_id,
            "currency": self.currency,
            "projected_minor": self.projected_minor,
            "ledger_minor": self.ledger_minor,
            "delta_minor": self.delta_minor,
        }


@dataclass(frozen=True, slots=True)
class ReconcileReport:
    checked: int
    discrepancies: list[WalletDiscrepancy]

    @property
    def ok(self) -> bool:
        return not self.discrepancies

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked": self.checked,
            "ok": self.ok,
            "discrepancies": [d.to_dict() for d in self.discrepancies],
        }


class ReconcileWalletBalances:
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self) -> ReconcileReport:
        checked = 0
        discrepancies: list[WalletDiscrepancy] = []

        with self._services.uow() as uow:
            after: EntityId | None = None
            while True:
                page = uow.wallets.list_all(limit=_PAGE, after=after)
                if not page:
                    break
                for wallet in page:
                    checked += 1
                    projected = wallet.balance.amount_minor
                    ledger = uow.ledger.wallet_balance(EntityId(str(wallet.id)))
                    if projected != ledger:
                        discrepancies.append(
                            WalletDiscrepancy(
                                wallet_id=str(wallet.id),
                                user_id=str(wallet.user_id),
                                currency=wallet.currency.code,
                                projected_minor=projected,
                                ledger_minor=ledger,
                                delta_minor=projected - ledger,
                            )
                        )
                if len(page) < _PAGE:
                    break
                after = EntityId(str(page[-1].id))

        return ReconcileReport(checked=checked, discrepancies=discrepancies)


__all__ = ["ReconcileReport", "ReconcileWalletBalances", "WalletDiscrepancy"]
