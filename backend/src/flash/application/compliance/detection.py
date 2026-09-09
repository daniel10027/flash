"""Détection AML (BE-076) : le job ``ScanForAmlAlerts`` parcourt les débits récents des
portefeuilles clients et ouvre une ``ComplianceAlert`` par règle déclenchée.

Trois règles, toutes paramétrables (``AmlThresholds``) :

* **CTR_THRESHOLD** — un débit unitaire ≥ ``ctr_threshold_minor``.
* **STRUCTURING** — au moins ``structuring_min_count`` débits chacun entre 70 % et 100 %
  du seuil sur ``structuring_window_hours`` et dont la somme dépasse le seuil.
* **VELOCITY** — sur ``velocity_window_hours`` : plus de ``velocity_max_count`` débits,
  ou un volume total ≥ ``velocity_max_volume_minor``.

Idempotent : ``ComplianceAlertRepository.exists_window`` empêche de rouvrir la même
alerte (clé = id de transaction pour CTR, jour calendaire sinon).
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from flash.application.services import AppServices
from flash.application.transaction import execute_in_uow
from flash.application.unit_of_work import WorkUnitOfWork
from flash.domain.compliance.alert import AlertKind, ComplianceAlert
from flash.domain.ledger.chart import Direction
from flash.domain.shared.identifiers import EntityId


@dataclass(frozen=True, slots=True)
class AmlThresholds:
    ctr_threshold_minor: int = 5_000_000
    lookback_hours: int = 72
    velocity_window_hours: int = 24
    velocity_max_count: int = 20
    velocity_max_volume_minor: int = 10_000_000
    structuring_window_hours: int = 48
    structuring_min_count: int = 3


@dataclass(frozen=True, slots=True)
class AmlScanReport:
    transactions_scanned: int
    accounts_flagged: int
    alerts_opened: int
    by_kind: dict[str, int]

    def to_dict(self) -> dict[str, Any]:
        return {
            "transactions_scanned": self.transactions_scanned,
            "accounts_flagged": self.accounts_flagged,
            "alerts_opened": self.alerts_opened,
            "by_kind": self.by_kind,
        }


@dataclass(frozen=True, slots=True)
class _Debit:
    txn_id: str
    at: datetime
    amount_minor: int


class ScanForAmlAlerts:
    def __init__(self, *, services: AppServices, thresholds: AmlThresholds) -> None:
        self._services = services
        self._t = thresholds

    def execute(self) -> AmlScanReport:
        now = self._services.clock.now()
        since = now - timedelta(hours=self._t.lookback_hours)
        counts = {"scanned": 0, "opened": 0}
        by_kind: dict[str, int] = defaultdict(int)
        flagged: set[str] = set()

        def work(uow: WorkUnitOfWork) -> None:
            wallet_owner: dict[str, EntityId] = {
                str(w.id): w.user_id for w in uow.wallets.list_all(limit=100_000)
            }
            per_user: dict[str, list[_Debit]] = defaultdict(list)

            for txn in uow.ledger.list_since(since):
                counts["scanned"] += 1
                for p in txn.postings:
                    if p.direction is not Direction.DEBIT or p.wallet_id is None:
                        continue
                    owner = wallet_owner.get(str(p.wallet_id))
                    if owner is None:
                        continue
                    per_user[str(owner)].append(
                        _Debit(str(txn.id), txn.occurred_at, p.amount.amount_minor)
                    )

            for user_str, debits in per_user.items():
                user_id = EntityId(user_str)
                debits.sort(key=lambda d: d.at)
                for kind, window_key, score, detail in self._rules(debits, now):
                    if uow.compliance_alerts.exists_window(user_id, kind.value, window_key):
                        continue
                    uow.compliance_alerts.add(
                        ComplianceAlert.open(
                            alert_id=self._services.ids.new_id(),
                            user_id=user_id,
                            kind=kind,
                            score=score,
                            detail=detail,
                            window_key=window_key,
                            now=now,
                        )
                    )
                    counts["opened"] += 1
                    by_kind[kind.value] += 1
                    flagged.add(user_str)

        execute_in_uow(self._services.uow, self._services.events, work)
        return AmlScanReport(
            transactions_scanned=counts["scanned"],
            accounts_flagged=len(flagged),
            alerts_opened=counts["opened"],
            by_kind=dict(by_kind),
        )

    def _rules(
        self, debits: list[_Debit], now: datetime
    ) -> list[tuple[AlertKind, str, int, dict[str, Any]]]:
        out: list[tuple[AlertKind, str, int, dict[str, Any]]] = []
        threshold = self._t.ctr_threshold_minor
        day = now.date().isoformat()

        for d in debits:
            if d.amount_minor >= threshold:
                out.append(
                    (
                        AlertKind.CTR_THRESHOLD,
                        d.txn_id,
                        90,
                        {"transaction_id": d.txn_id, "amount_minor": d.amount_minor},
                    )
                )

        near = [
            d
            for d in debits
            if int(threshold * 0.7) <= d.amount_minor < threshold
            and now - d.at <= timedelta(hours=self._t.structuring_window_hours)
        ]
        if len(near) >= self._t.structuring_min_count and sum(
            d.amount_minor for d in near
        ) >= threshold:
            out.append(
                (
                    AlertKind.STRUCTURING,
                    f"struct:{day}",
                    80,
                    {
                        "count": len(near),
                        "total_minor": sum(d.amount_minor for d in near),
                        "window_hours": self._t.structuring_window_hours,
                    },
                )
            )

        vel = [
            d
            for d in debits
            if now - d.at <= timedelta(hours=self._t.velocity_window_hours)
        ]
        vol = sum(d.amount_minor for d in vel)
        if len(vel) >= self._t.velocity_max_count or vol >= self._t.velocity_max_volume_minor:
            out.append(
                (
                    AlertKind.VELOCITY,
                    f"vel:{day}",
                    70,
                    {
                        "count": len(vel),
                        "volume_minor": vol,
                        "window_hours": self._t.velocity_window_hours,
                    },
                )
            )
        return out


__all__ = ["AmlScanReport", "AmlThresholds", "ScanForAmlAlerts"]
