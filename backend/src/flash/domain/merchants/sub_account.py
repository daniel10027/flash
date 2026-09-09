"""Agrégat ``MerchantSubAccount`` — une **caisse** ou un **employé** d'un marchand
(reste de BE-068).

C'est une **étiquette d'attribution** : un sous-compte n'a ni portefeuille ni compte
ledger propre. Les paiements encaissés portent éventuellement son ``id`` pour un relevé
par caisse / par employé ; le net et le règlement restent au niveau du marchand.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from flash.domain.merchants.events import (
    MerchantSubAccountOpened,
    MerchantSubAccountUpdated,
)
from flash.domain.shared.errors import InvalidInput
from flash.domain.shared.events import EventRecorder
from flash.domain.shared.identifiers import EntityId

_MAX_LABEL = 60
_MAX_REF = 40


class SubAccountKind(StrEnum):
    TILL = "TILL"  # caisse / point de vente
    EMPLOYEE = "EMPLOYEE"  # collaborateur qui encaisse


class MerchantSubAccount(EventRecorder):
    def __init__(
        self,
        *,
        id: EntityId,
        merchant_id: EntityId,
        kind: SubAccountKind,
        label: str,
        created_at: datetime,
        external_ref: str | None = None,
        active: bool = True,
    ) -> None:
        super().__init__()
        cleaned = label.strip()
        if not cleaned:
            raise InvalidInput("Un libellé est requis pour la caisse / l'employé.")
        if len(cleaned) > _MAX_LABEL:
            raise InvalidInput(f"Libellé trop long (max {_MAX_LABEL}).")
        ref = (external_ref or "").strip() or None
        if ref is not None and len(ref) > _MAX_REF:
            raise InvalidInput(f"Référence externe trop longue (max {_MAX_REF}).")
        self.id = id
        self.merchant_id = merchant_id
        self.kind = kind
        self.label = cleaned
        self.external_ref = ref
        self.active = active
        self.created_at = created_at

    @classmethod
    def open(
        cls,
        *,
        sub_account_id: EntityId,
        merchant_id: EntityId,
        kind: SubAccountKind,
        label: str,
        now: datetime,
        external_ref: str | None = None,
    ) -> MerchantSubAccount:
        sub = cls(
            id=sub_account_id,
            merchant_id=merchant_id,
            kind=kind,
            label=label,
            created_at=now,
            external_ref=external_ref,
        )
        sub.record_event(
            MerchantSubAccountOpened(
                occurred_at=now,
                aggregate_id=str(sub_account_id),
                merchant_id=str(merchant_id),
                kind=kind.value,
                label=sub.label,
            )
        )
        return sub

    def update(
        self,
        *,
        now: datetime,
        label: str | None = None,
        external_ref: str | None = None,
        active: bool | None = None,
    ) -> None:
        if label is not None:
            cleaned = label.strip()
            if not cleaned:
                raise InvalidInput("Le libellé ne peut pas être vide.")
            if len(cleaned) > _MAX_LABEL:
                raise InvalidInput(f"Libellé trop long (max {_MAX_LABEL}).")
            self.label = cleaned
        if external_ref is not None:
            ref = external_ref.strip() or None
            if ref is not None and len(ref) > _MAX_REF:
                raise InvalidInput(f"Référence externe trop longue (max {_MAX_REF}).")
            self.external_ref = ref
        if active is not None:
            self.active = active
        self.record_event(
            MerchantSubAccountUpdated(
                occurred_at=now,
                aggregate_id=str(self.id),
                merchant_id=str(self.merchant_id),
                active=self.active,
                label=self.label,
            )
        )

    def ensure_usable(self) -> None:
        if not self.active:
            raise InvalidInput("Cette caisse / cet employé est désactivé(e).")

    def __repr__(self) -> str:
        return (
            f"MerchantSubAccount(id={self.id!s}, kind={self.kind.value}, "
            f"label={self.label!r}, active={self.active})"
        )


__all__ = ["MerchantSubAccount", "SubAccountKind"]
