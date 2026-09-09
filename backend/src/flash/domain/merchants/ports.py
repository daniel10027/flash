"""Ports du sous-domaine marchands."""

from __future__ import annotations

from datetime import datetime
from typing import Protocol, runtime_checkable

from flash.domain.merchants.api_key import MerchantApiKey
from flash.domain.merchants.charge import MerchantCharge
from flash.domain.merchants.merchant import Merchant
from flash.domain.merchants.payment import MerchantPayment
from flash.domain.merchants.settlement import MerchantSettlement
from flash.domain.merchants.webhook import MerchantWebhookDelivery
from flash.domain.shared.identifiers import EntityId


@runtime_checkable
class MerchantRepository(Protocol):
    def get(self, merchant_id: EntityId) -> Merchant | None: ...

    def get_by_user_id(self, user_id: EntityId) -> Merchant | None: ...

    def get_for_update(self, merchant_id: EntityId) -> Merchant:
        """Marchand avec verrou pessimiste. Lève ``KeyError`` si absent."""
        ...

    def list_due_for_settlement(
        self, now: datetime, *, limit: int = 500
    ) -> list[Merchant]:
        """Marchands ``ACTIVE`` avec compte bancaire dont ``next_settlement_at`` est échu."""
        ...

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

    def list_settleable(self, merchant_id: EntityId) -> list[MerchantPayment]:
        """Paiements ``COMPLETED`` non encore rattachés à un règlement."""
        ...

    def list_for_settlement(self, settlement_id: EntityId) -> list[MerchantPayment]: ...

    def add(self, payment: MerchantPayment) -> None: ...

    def save(self, payment: MerchantPayment) -> None: ...


@runtime_checkable
class MerchantSettlementRepository(Protocol):
    def get(self, settlement_id: EntityId) -> MerchantSettlement | None: ...

    def list_for_merchant(self, merchant_id: EntityId) -> list[MerchantSettlement]: ...

    def add(self, settlement: MerchantSettlement) -> None: ...

    def save(self, settlement: MerchantSettlement) -> None: ...


@runtime_checkable
class MerchantApiKeyRepository(Protocol):
    def get(self, key_id: EntityId) -> MerchantApiKey | None: ...

    def get_by_prefix(self, prefix: str) -> MerchantApiKey | None: ...

    def list_for_merchant(self, merchant_id: EntityId) -> list[MerchantApiKey]: ...

    def add(self, api_key: MerchantApiKey) -> None: ...

    def save(self, api_key: MerchantApiKey) -> None: ...


@runtime_checkable
class MerchantWebhookDeliveryRepository(Protocol):
    def get(self, delivery_id: EntityId) -> MerchantWebhookDelivery | None: ...

    def exists_for_source(self, event_type: str, source_id: EntityId) -> bool:
        """Vrai si une livraison existe déjà pour ce couple (type, agrégat source).

        ``source_id`` = id du paiement marchand qui a produit l'événement ; garantit
        l'idempotence de la mise en file par le job de scan.
        """
        ...

    def list_due(
        self, now: datetime, *, limit: int = 200
    ) -> list[MerchantWebhookDelivery]: ...

    def add(self, delivery: MerchantWebhookDelivery) -> None: ...

    def save(self, delivery: MerchantWebhookDelivery) -> None: ...


__all__ = [
    "MerchantApiKeyRepository",
    "MerchantChargeRepository",
    "MerchantPaymentRepository",
    "MerchantRepository",
    "MerchantSettlementRepository",
    "MerchantWebhookDeliveryRepository",
]
