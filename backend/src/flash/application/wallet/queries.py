"""Lecture des portefeuilles (BE-030).

Les soldes viennent de la projection maintenue par le ledger. ``available`` exclut les
fonds réservés (retrait cash en attente, autorisation carte…).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flash.application.services import AppServices
from flash.application.use_case import Command, UseCase
from flash.domain.shared.errors import WalletNotFound
from flash.domain.shared.identifiers import EntityId
from flash.domain.wallet.wallet import Wallet


@dataclass(frozen=True, slots=True)
class WalletView:
    id: str
    currency: str
    status: str
    available_minor: int
    reserved_minor: int
    vaulted_minor: int
    saved_minor: int
    balance_minor: int
    created_at: str

    @classmethod
    def of(cls, wallet: Wallet) -> WalletView:
        return cls(
            id=str(wallet.id),
            currency=wallet.currency.code,
            status=wallet.status.value,
            available_minor=wallet.available.amount_minor,
            reserved_minor=wallet.reserved.amount_minor,
            vaulted_minor=wallet.vaulted.amount_minor,
            saved_minor=wallet.saved.amount_minor,
            balance_minor=wallet.balance.amount_minor,
            created_at=wallet.created_at.isoformat(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "currency": self.currency,
            "status": self.status,
            "available_minor": self.available_minor,
            "reserved_minor": self.reserved_minor,
            "vaulted_minor": self.vaulted_minor,
            "saved_minor": self.saved_minor,
            "balance_minor": self.balance_minor,
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class ListWalletsCommand(Command):
    user_id: str


class ListWallets(UseCase[ListWalletsCommand, list[WalletView]]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: ListWalletsCommand) -> list[WalletView]:
        with self._services.uow() as uow:
            wallets = uow.wallets.list_for_user(EntityId(command.user_id))
            return [WalletView.of(w) for w in wallets]


@dataclass(frozen=True, slots=True)
class GetWalletCommand(Command):
    user_id: str
    wallet_id: str


class GetWallet(UseCase[GetWalletCommand, WalletView]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: GetWalletCommand) -> WalletView:
        with self._services.uow() as uow:
            wallet = uow.wallets.get(EntityId(command.wallet_id))
            if wallet is None or str(wallet.user_id) != command.user_id:
                raise WalletNotFound()
            return WalletView.of(wallet)


__all__ = [
    "GetWallet",
    "GetWalletCommand",
    "ListWallets",
    "ListWalletsCommand",
    "WalletView",
]
