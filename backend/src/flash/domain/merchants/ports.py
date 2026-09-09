"""Ports du sous-domaine marchands."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from flash.domain.merchants.charge import MerchantCharge
from flash.domain.merchants.merchant import Merchant
from flash.domain.merchants.payment import MerchantPayment
from flash.domain.shared.identifiers import EntityId


@runtime_checkable
class MerchantRepository(Protocol):
    def get(self, merchant_id: EntityId) -> Merchant | None: ...

    def get_by_user_id(self, user_id: EntityId) -> Merchant | None: ...

    def add(self, merchant: Merchant) -> None: ...

    def save(self, merchant: Merchant) -> None: ...


@runtime_checkable
class MerchantChargeRepository(Protocol):
    def get(self, charge_id: EntityId) -> MerchantCharge | None: ...

    def get_for_update(self, charge_id: EntityId) -> MerchantCharge:
        """Charge avec verrou pessimiste. Lève ``KeyError`` si absente."""
        ...

    def list_for_merchant(self, merchant_id: EntityId) -> list[MerchantCharge]: ...

    def list_expired(self, now: datetime, *, limit: int = 500) -> list[MerchantCharge]:
        """QR dynamiques ``PENDING`` dont ``expires_at`` est dépassé (job d'expiration)."""
        ...

    def add(self, charge: MerchantCharge) -> None: ...

    def save(self, charge: MerchantCharge) -> None: ...


@runtime_checkable
class MerchantPaymentRepository(Protocol):
    def get(self, payment_id: EntityId) -> MerchantPayment | None: ...

    def get_by_ledger_transaction_id(self, txn_id: EntityId) -> MerchantPayment | None: ...

    def list_for_merchant(self, merchant_id: EntityId) -> list[MerchantPayment]: ...

    def add(self, payment: MerchantPayment) -> None: ...

    def save(self, payment: MerchantPayment) -> None: ...


__all__ = [
    "MerchantChargeRepository",
    "MerchantPaymentRepository",
    "MerchantRepository",
]
