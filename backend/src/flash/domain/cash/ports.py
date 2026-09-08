"""Port du sous-domaine cash (ordres de dépôt / retrait)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from flash.domain.cash.order import CashOrder
from flash.domain.shared.identifiers import EntityId


@runtime_checkable
class CashOrderRepository(Protocol):
    def get(self, order_id: EntityId) -> CashOrder | None: ...

    def get_pending_withdrawal_by_code_hash(self, code_hash: str) -> CashOrder | None:
        """Retrouve un retrait ``INITIATED`` par l'empreinte de son code."""
        ...

    def add(self, order: CashOrder) -> None: ...

    def save(self, order: CashOrder) -> None: ...


__all__ = ["CashOrderRepository"]
