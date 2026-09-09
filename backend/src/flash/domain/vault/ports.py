"""Port du sous-domaine coffre (agrégat ``Vault``, un par portefeuille)."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from flash.domain.shared.identifiers import EntityId
from flash.domain.vault.vault import Vault


@runtime_checkable
class VaultRepository(Protocol):
    def get_for_wallet(self, wallet_id: EntityId) -> Vault | None:
        """Le coffre adossé à ce portefeuille, poches comprises, ou ``None``."""
        ...

    def get_for_user(self, user_id: EntityId) -> Vault | None:
        """Le coffre du portefeuille principal de l'utilisateur, ou ``None``."""
        ...

    def add(self, vault: Vault) -> None: ...

    def save(self, vault: Vault) -> None: ...


__all__ = ["VaultRepository"]
