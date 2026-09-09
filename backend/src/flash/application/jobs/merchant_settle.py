"""Job de règlement marchand (BE-070), à appeler par cron via ``flash run-jobs``.

Pour chaque marchand ``ACTIVE`` avec compte bancaire dont ``next_settlement_at`` est
échu : règle le net accumulé, avance l'échéance. Idempotent dans les faits (relancé, il
ne trouve plus de marchand échu ni de paiement non réglé).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flash.application.merchants.bank import BankGateway
from flash.application.merchants.settlement import settle_merchant
from flash.application.services import AppServices
from flash.application.transaction import execute_in_uow
from flash.application.unit_of_work import WorkUnitOfWork
from flash.domain.merchants.settlement import MerchantSettlementStatus


@dataclass(frozen=True, slots=True)
class MerchantSettlementReport:
    checked: int
    settled: int
    skipped: int
    failed: int
    settled_minor: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "checked": self.checked,
            "settled": self.settled,
            "skipped": self.skipped,
            "failed": self.failed,
            "settled_minor": self.settled_minor,
        }


class SettleDueMerchants:
    def __init__(self, *, services: AppServices, bank: BankGateway) -> None:
        self._services = services
        self._bank = bank

    def execute(self) -> MerchantSettlementReport:
        now = self._services.clock.now()
        counts = {"checked": 0, "settled": 0, "skipped": 0, "failed": 0, "minor": 0}

        def work(uow: WorkUnitOfWork) -> None:
            for merchant in uow.merchants.list_due_for_settlement(now):
                counts["checked"] += 1
                settlement = settle_merchant(
                    uow,
                    merchant,
                    bank=self._bank,
                    ids=self._services.ids,
                    clock=self._services.clock,
                )
                if settlement is None:
                    counts["skipped"] += 1
                elif settlement.status is MerchantSettlementStatus.PAID:
                    counts["settled"] += 1
                    counts["minor"] += settlement.amount.amount_minor
                else:
                    counts["failed"] += 1

        execute_in_uow(self._services.uow, self._services.events, work)
        return MerchantSettlementReport(
            checked=counts["checked"],
            settled=counts["settled"],
            skipped=counts["skipped"],
            failed=counts["failed"],
            settled_minor=counts["minor"],
        )


__all__ = ["MerchantSettlementReport", "SettleDueMerchants"]
