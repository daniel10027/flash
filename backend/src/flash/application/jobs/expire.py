"""Job d'expiration (BE-044) — passe les opérations en attente périmées à l'état expiré.

- Retraits cash ``INITIATED`` dont le code a expiré : ``CashOrder.expire`` **et**
  libération de la réserve sur le portefeuille du client.
- Demandes de paiement ``PENDING`` périmées : ``PaymentRequest.expire``.
- QR marchands dynamiques ``PENDING`` périmés : ``MerchantCharge.expire``.

Idempotent : relancé, il ne trouve plus rien à faire.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flash.application.services import AppServices
from flash.application.transaction import execute_in_uow
from flash.application.unit_of_work import WorkUnitOfWork
from flash.domain.shared.errors import InvalidInput
from flash.domain.shared.identifiers import EntityId


@dataclass(frozen=True, slots=True)
class ExpireReport:
    withdrawals_expired: int
    payment_requests_expired: int
    merchant_charges_expired: int

    @property
    def total(self) -> int:
        return (
            self.withdrawals_expired + self.payment_requests_expired + self.merchant_charges_expired
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "withdrawals_expired": self.withdrawals_expired,
            "payment_requests_expired": self.payment_requests_expired,
            "merchant_charges_expired": self.merchant_charges_expired,
            "total": self.total,
        }


class ExpireStaleOperations:
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self) -> ExpireReport:
        now = self._services.clock.now()
        counts = {"wdl": 0, "req": 0, "chg": 0}

        def work(uow: WorkUnitOfWork) -> None:
            for order in uow.cash_orders.list_expired_withdrawals(now):
                wallets = uow.wallets.list_for_user(order.client_id)
                if not wallets:  # pragma: no cover - intégrité référentielle
                    raise InvalidInput("Aucun portefeuille pour ce compte.")
                wallet = uow.wallets.get_for_update(EntityId(str(wallets[0].id)))
                # le retrait a réservé montant + frais ; on rend la réserve
                order.expire(now)
                wallet.release(order.total, now)
                uow.cash_orders.save(order)
                uow.wallets.save(wallet)
                counts["wdl"] += 1

            for request in uow.payment_requests.list_expired(now):
                request.expire(now)
                uow.payment_requests.save(request)
                counts["req"] += 1

            for charge in uow.merchant_charges.list_expired(now):
                charge.expire(now)
                uow.merchant_charges.save(charge)
                counts["chg"] += 1

        execute_in_uow(self._services.uow, self._services.events, work)
        return ExpireReport(
            withdrawals_expired=counts["wdl"],
            payment_requests_expired=counts["req"],
            merchant_charges_expired=counts["chg"],
        )


__all__ = ["ExpireReport", "ExpireStaleOperations"]
