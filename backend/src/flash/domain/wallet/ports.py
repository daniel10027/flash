"""Ports du sous-domaine wallet."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import Currency
from flash.domain.wallet.wallet import Wallet


@runtime_checkable
class WalletRepository(Protocol):
    """Persistance de l'agrégat ``Wallet`` et de sa projection de solde."""

    def get(self, wallet_id: EntityId) -> Wallet | None: ...

    def get_for_user(self, user_id: EntityId, currency: Currency) -> Wallet | None: ...

    def list_for_user(self, user_id: EntityId) -> list[Wallet]: ...

    def get_for_update(self, wallet_id: EntityId) -> Wallet:
        """Charge le wallet avec un verrou pessimiste (``SELECT … FOR UPDATE``).

        À utiliser dans tout cas d'usage qui débite/réserve, pour interdire deux
        mouvements concurrents de passer le solde en négatif. Lève ``KeyError`` si le
        wallet n'existe pas.
        """
        ...

    def add(self, wallet: Wallet) -> None: ...

    def save(self, wallet: Wallet) -> None: ...


__all__ = ["WalletRepository"]
