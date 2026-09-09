"""Entité ``MerchantApiKey`` — jeton d'accès à l'API marchande publique (BE-069).

Le secret **en clair n'est jamais stocké** : seul son empreinte (``secret_hash``, calculée
par un adaptateur d'infrastructure) et un ``prefix`` non sensible affiché au marchand pour
reconnaître la clé. Une clé se révoque, jamais ne se réactive.
"""

from __future__ import annotations

from datetime import datetime

from flash.domain.merchants.events import MerchantApiKeyIssued, MerchantApiKeyRevoked
from flash.domain.shared.errors import InvalidAccountState, InvalidInput
from flash.domain.shared.events import EventRecorder
from flash.domain.shared.identifiers import EntityId

_MAX_LABEL = 60


class MerchantApiKey(EventRecorder):
    def __init__(
        self,
        *,
        id: EntityId,
        merchant_id: EntityId,
        prefix: str,
        secret_hash: str,
        label: str,
        created_at: datetime,
        last_used_at: datetime | None = None,
        revoked_at: datetime | None = None,
    ) -> None:
        super().__init__()
        if not prefix.strip():
            raise InvalidInput("Préfixe de clé manquant.")
        if not secret_hash.strip():
            raise InvalidInput("Empreinte de clé manquante.")
        self.id = id
        self.merchant_id = merchant_id
        self.prefix = prefix
        self.secret_hash = secret_hash
        self.label = label.strip() or "sans nom"
        self.created_at = created_at
        self.last_used_at = last_used_at
        self.revoked_at = revoked_at

    @classmethod
    def issue(
        cls,
        *,
        key_id: EntityId,
        merchant_id: EntityId,
        prefix: str,
        secret_hash: str,
        label: str,
        now: datetime,
    ) -> MerchantApiKey:
        if len(label) > _MAX_LABEL:
            raise InvalidInput("Le libellé de la clé est trop long (60 caractères max).")
        key = cls(
            id=key_id,
            merchant_id=merchant_id,
            prefix=prefix,
            secret_hash=secret_hash,
            label=label,
            created_at=now,
        )
        key.record_event(
            MerchantApiKeyIssued(
                occurred_at=now,
                aggregate_id=str(key_id),
                merchant_id=str(merchant_id),
                key_prefix=prefix,
                label=key.label,
            )
        )
        return key

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None

    def mark_used(self, now: datetime) -> None:
        self.last_used_at = now

    def revoke(self, now: datetime) -> None:
        if self.revoked_at is not None:
            raise InvalidAccountState("Cette clé est déjà révoquée.", status="REVOKED")
        self.revoked_at = now
        self.record_event(
            MerchantApiKeyRevoked(
                occurred_at=now,
                aggregate_id=str(self.id),
                merchant_id=str(self.merchant_id),
                key_prefix=self.prefix,
            )
        )

    def __repr__(self) -> str:
        state = "active" if self.is_active else "révoquée"
        return f"MerchantApiKey(prefix={self.prefix!r}, {state})"


__all__ = ["MerchantApiKey"]
