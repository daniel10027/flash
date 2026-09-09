"""Port du sous-domaine interop opérateurs."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from flash.domain.operators.transfer import OperatorTransfer
from flash.domain.shared.identifiers import EntityId


@runtime_checkable
class OperatorTransferRepository(Protocol):
    def get(self, transfer_id: EntityId) -> OperatorTransfer | None: ...

    def get_by_reference(self, reference: str) -> OperatorTransfer | None: ...

    def get_for_update_by_reference(self, reference: str) -> OperatorTransfer:
        """Transfert (verrou pessimiste) par sa référence Flash. Lève ``KeyError``."""
        ...

    def list_for_user(self, user_id: EntityId) -> list[OperatorTransfer]: ...

    def add(self, transfer: OperatorTransfer) -> None: ...

    def save(self, transfer: OperatorTransfer) -> None: ...


__all__ = ["OperatorTransferRepository"]
