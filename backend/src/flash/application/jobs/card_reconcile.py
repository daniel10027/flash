"""Rapprochement carte (BE-059) — lecture seule.

Pour chaque autorisation résolue (``CAPTURED`` / ``REFUNDED``), on vérifie qu'il existe
l'écriture ledger attendue, équilibrée, et de bon montant net sur le portefeuille du
titulaire (``CARDCAP-<id>`` pour la capture, ``CARDREF-<id>`` pour le remboursement).
Tout écart est **signalé** ; rien n'est corrigé automatiquement.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flash.application.services import AppServices
from flash.domain.ledger.chart import Direction
from flash.domain.ledger.transaction import LedgerTransaction
from flash.domain.shared.identifiers import EntityId

_PAGE = 500


def _wallet_net_minor(txn: LedgerTransaction, wallet_id: str) -> int:
    net = 0
    for p in txn.postings:
        if p.wallet_id is not None and str(p.wallet_id) == wallet_id:
            net += (
                -p.amount.amount_minor
                if p.direction is Direction.DEBIT
                else p.amount.amount_minor
            )
    return net


@dataclass(frozen=True, slots=True)
class CardDiscrepancy:
    authorization_id: str
    card_id: str
    issue: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "authorization_id": self.authorization_id,
            "card_id": self.card_id,
            "issue": self.issue,
        }


@dataclass(frozen=True, slots=True)
class CardReconcileReport:
    checked: int
    discrepancies: list[CardDiscrepancy]

    @property
    def ok(self) -> bool:
        return not self.discrepancies

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked": self.checked,
            "ok": self.ok,
            "discrepancies": [d.to_dict() for d in self.discrepancies],
        }


class ReconcileCardSettlements:
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self) -> CardReconcileReport:
        checked = 0
        issues: list[CardDiscrepancy] = []

        with self._services.uow() as uow:
            after: EntityId | None = None
            while True:
                page = uow.card_authorizations.list_resolved(limit=_PAGE, after=after)
                if not page:
                    break
                for auth in page:
                    checked += 1
                    wallet_id = str(auth.wallet_id)
                    expected = auth.captured_minor or 0
                    issues.extend(
                        self._check(
                            uow,
                            auth_id=auth.authorization_id,
                            card_id=str(auth.card_id),
                            wallet_id=wallet_id,
                            reference=f"CARDCAP-{auth.authorization_id}",
                            expected_net=-expected,
                            label="capture",
                        )
                    )
                    if auth.status.value == "REFUNDED":
                        issues.extend(
                            self._check(
                                uow,
                                auth_id=auth.authorization_id,
                                card_id=str(auth.card_id),
                                wallet_id=wallet_id,
                                reference=f"CARDREF-{auth.authorization_id}",
                                expected_net=expected,
                                label="remboursement",
                            )
                        )
                if len(page) < _PAGE:
                    break
                after = EntityId(str(page[-1].id))

        return CardReconcileReport(checked=checked, discrepancies=issues)

    def _check(
        self,
        uow: Any,
        *,
        auth_id: str,
        card_id: str,
        wallet_id: str,
        reference: str,
        expected_net: int,
        label: str,
    ) -> list[CardDiscrepancy]:
        txns = uow.ledger.get_by_reference(reference)
        if len(txns) != 1:
            return [
                CardDiscrepancy(
                    auth_id, card_id, f"{label} : {len(txns)} écriture(s) pour {reference}"
                )
            ]
        txn = txns[0]
        if not txn.is_balanced:  # pragma: no cover - une LedgerTransaction ne peut pas l'être
            return [CardDiscrepancy(auth_id, card_id, f"{label} : écriture déséquilibrée")]
        net = _wallet_net_minor(txn, wallet_id)
        if net != expected_net:
            return [
                CardDiscrepancy(
                    auth_id, card_id, f"{label} : net {net} attendu {expected_net}"
                )
            ]
        return []


__all__ = ["CardDiscrepancy", "CardReconcileReport", "ReconcileCardSettlements"]
