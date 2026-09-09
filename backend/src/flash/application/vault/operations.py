"""Cas d'usage du coffre (BE-047 → BE-049).

Le coffre range de l'argent du portefeuille dans des **poches** verrouillables. Un
mouvement de poche est instantané, **sans frais**, et toujours adossé à une
``LedgerTransaction.vault_move`` équilibrée entre l'analytique ``client_liability`` et
``savings_liability`` (poche). Le contenu du coffre reste une dette de Flash envers le
client : il compte dans ``wallet.balance`` mais pas dans ``wallet.available``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from flash.application.idempotency import IdempotencyGuard
from flash.application.services import AppServices
from flash.application.transaction import execute_in_uow
from flash.application.unit_of_work import WorkUnitOfWork
from flash.application.use_case import Command, UseCase
from flash.domain.ledger.chart import AccountType
from flash.domain.ledger.transaction import LedgerTransaction
from flash.domain.shared.errors import InvalidInput
from flash.domain.shared.identifiers import EntityId, IdempotencyKey
from flash.domain.shared.money import Money
from flash.domain.vault.vault import Vault, VaultPocket

_ROUTE_DEPOSIT = "POST /v1/vault/pockets/{id}/deposit"
_ROUTE_WITHDRAW = "POST /v1/vault/pockets/{id}/withdraw"


# --------------------------------------------------------------------- vues
@dataclass(frozen=True, slots=True)
class VaultPocketView:
    pocket_id: str
    name: str
    balance_minor: int
    currency: str
    goal_minor: int | None
    progress_bps: int | None
    locked_until: str | None
    created_at: str

    @classmethod
    def of(cls, pocket: VaultPocket, currency: str) -> VaultPocketView:
        return cls(
            pocket_id=str(pocket.id),
            name=pocket.name,
            balance_minor=pocket.balance.amount_minor,
            currency=currency,
            goal_minor=pocket.goal_minor,
            progress_bps=pocket.progress_bps,
            locked_until=pocket.locked_until.isoformat() if pocket.locked_until else None,
            created_at=pocket.created_at.isoformat(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "pocket_id": self.pocket_id,
            "name": self.name,
            "balance_minor": self.balance_minor,
            "currency": self.currency,
            "goal_minor": self.goal_minor,
            "progress_bps": self.progress_bps,
            "locked_until": self.locked_until,
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class VaultView:
    currency: str
    vaulted_minor: int
    pockets: list[VaultPocketView]

    @classmethod
    def of(cls, vault: Vault | None, *, currency: str) -> VaultView:
        if vault is None:
            return cls(currency=currency, vaulted_minor=0, pockets=[])
        return cls(
            currency=currency,
            vaulted_minor=vault.total.amount_minor,
            pockets=[VaultPocketView.of(p, currency) for p in vault.pockets],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "currency": self.currency,
            "vaulted_minor": self.vaulted_minor,
            "pockets": [p.to_dict() for p in self.pockets],
        }


@dataclass(frozen=True, slots=True)
class VaultMoveReceipt:
    pocket_id: str
    pocket_name: str
    direction: str  # "in" (vers le coffre) | "out" (depuis le coffre)
    amount_minor: int
    currency: str
    wallet_available_after_minor: int
    pocket_balance_after_minor: int
    vaulted_after_minor: int
    occurred_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "pocket_id": self.pocket_id,
            "pocket_name": self.pocket_name,
            "direction": self.direction,
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "wallet_available_after_minor": self.wallet_available_after_minor,
            "pocket_balance_after_minor": self.pocket_balance_after_minor,
            "vaulted_after_minor": self.vaulted_after_minor,
            "occurred_at": self.occurred_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> VaultMoveReceipt:
        return cls(**{k: data[k] for k in cls.__dataclass_fields__})


# --------------------------------------------------------------------- helpers
def _load_user_wallet(uow: WorkUnitOfWork, user_id: str) -> tuple[Any, Any]:
    user = uow.users.get(EntityId(user_id))
    if user is None:  # pragma: no cover - jeton valide
        raise InvalidInput("Compte introuvable.")
    user.ensure_can_transact()
    wallets = uow.wallets.list_for_user(user.id)
    if not wallets:  # pragma: no cover - un compte a toujours son portefeuille
        raise InvalidInput("Aucun portefeuille pour ce compte.")
    wallet = uow.wallets.get_for_update(EntityId(str(wallets[0].id)))
    return user, wallet


def _parse_locked_until(raw: str | None) -> datetime | None:
    if raw is None or not raw.strip():
        return None
    try:
        parsed = datetime.fromisoformat(raw.strip())
    except ValueError as exc:
        raise InvalidInput("Date de verrouillage invalide (format ISO 8601 attendu).") from exc
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=UTC)


# ============================================================== consulter
@dataclass(frozen=True, slots=True)
class GetVaultCommand(Command):
    user_id: str


class GetVault(UseCase[GetVaultCommand, VaultView]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: GetVaultCommand) -> VaultView:
        with self._services.uow() as uow:
            _, wallet = _load_user_wallet(uow, command.user_id)
            vault = uow.vaults.get_for_wallet(EntityId(str(wallet.id)))
            return VaultView.of(vault, currency=wallet.currency.code)


# ============================================================== ouvrir une poche
@dataclass(frozen=True, slots=True)
class OpenVaultPocketCommand(Command):
    user_id: str
    name: str
    goal_minor: int | None = None
    locked_until: str | None = None


class OpenVaultPocket(UseCase[OpenVaultPocketCommand, VaultPocketView]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: OpenVaultPocketCommand) -> VaultPocketView:
        if not command.name.strip():
            raise InvalidInput("Le nom de la poche est requis.")
        if command.goal_minor is not None and command.goal_minor <= 0:
            raise InvalidInput("L'objectif doit être strictement positif.")
        locked_until = _parse_locked_until(command.locked_until)
        now = self._services.clock.now()
        vault_id = self._services.ids.new_id()
        pocket_id = self._services.ids.new_id()
        captured: list[VaultPocketView] = []

        def work(uow: WorkUnitOfWork) -> None:
            user, wallet = _load_user_wallet(uow, command.user_id)
            vault = uow.vaults.get_for_wallet(EntityId(str(wallet.id)))
            is_new = vault is None
            if vault is None:
                vault = Vault.for_wallet(
                    vault_id=vault_id,
                    wallet_id=EntityId(str(wallet.id)),
                    user_id=user.id,
                    currency=wallet.currency,
                    now=now,
                )
            pocket = vault.open_pocket(
                pocket_id=pocket_id,
                name=command.name,
                now=now,
                goal_minor=command.goal_minor,
                locked_until=locked_until,
            )
            if is_new:
                uow.vaults.add(vault)
            else:
                uow.vaults.save(vault)
            captured.append(VaultPocketView.of(pocket, wallet.currency.code))

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


# ============================================================== renommer
@dataclass(frozen=True, slots=True)
class RenameVaultPocketCommand(Command):
    user_id: str
    pocket_id: str
    name: str


class RenameVaultPocket(UseCase[RenameVaultPocketCommand, VaultPocketView]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: RenameVaultPocketCommand) -> VaultPocketView:
        if not command.name.strip():
            raise InvalidInput("Le nom de la poche est requis.")
        now = self._services.clock.now()
        captured: list[VaultPocketView] = []

        def work(uow: WorkUnitOfWork) -> None:
            _, wallet = _load_user_wallet(uow, command.user_id)
            vault = _require_vault(uow, wallet)
            vault.rename_pocket(
                pocket_id=EntityId(command.pocket_id), name=command.name, now=now
            )
            uow.vaults.save(vault)
            captured.append(
                VaultPocketView.of(vault.pocket(EntityId(command.pocket_id)), wallet.currency.code)
            )

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


# ============================================================== fermer (vide)
@dataclass(frozen=True, slots=True)
class CloseVaultPocketCommand(Command):
    user_id: str
    pocket_id: str


class CloseVaultPocket(UseCase[CloseVaultPocketCommand, None]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: CloseVaultPocketCommand) -> None:
        now = self._services.clock.now()

        def work(uow: WorkUnitOfWork) -> None:
            _, wallet = _load_user_wallet(uow, command.user_id)
            vault = _require_vault(uow, wallet)
            vault.close_pocket(pocket_id=EntityId(command.pocket_id), now=now)
            uow.vaults.save(vault)

        execute_in_uow(self._services.uow, self._services.events, work)


# ============================================================== alimenter / reprendre
@dataclass(frozen=True, slots=True)
class MoveToVaultCommand(Command):
    user_id: str
    pocket_id: str
    amount_minor: int
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class MoveFromVaultCommand(Command):
    user_id: str
    pocket_id: str
    amount_minor: int
    idempotency_key: str


class _VaultMove:
    """Corps commun aux deux sens du mouvement de coffre."""

    def __init__(self, *, services: AppServices, into_vault: bool) -> None:
        self._services = services
        self._into_vault = into_vault
        self._guard = IdempotencyGuard(services.idempotency)

    def run(
        self, *, user_id: str, pocket_id: str, amount_minor: int, idempotency_key: str
    ) -> VaultMoveReceipt:
        if amount_minor <= 0:
            raise InvalidInput("Le montant doit être strictement positif.")
        try:
            key = IdempotencyKey(idempotency_key)
        except ValueError as exc:
            raise InvalidInput(str(exc)) from exc

        route = _ROUTE_DEPOSIT if self._into_vault else _ROUTE_WITHDRAW
        outcome = self._guard.run(
            key=key,
            subject=user_id,
            route=route,
            produce=lambda: self._move(user_id, pocket_id, amount_minor),
            rebuild=VaultMoveReceipt.from_dict,
        )
        return outcome.result

    def _move(
        self, user_id: str, pocket_id: str, amount_minor: int
    ) -> tuple[VaultMoveReceipt, dict[str, Any]]:
        now = self._services.clock.now()
        txn_id = self._services.ids.new_id()
        captured: dict[str, Any] = {}

        def work(uow: WorkUnitOfWork) -> None:
            _, wallet = _load_user_wallet(uow, user_id)
            vault = _require_vault(uow, wallet)
            pocket = vault.pocket(EntityId(pocket_id))
            amount = Money(amount_minor, wallet.currency)

            client_acc = uow.ledger.ensure_account(
                account_type=AccountType.CLIENT_LIABILITY,
                currency=wallet.currency,
                owner_ref=str(wallet.user_id),
            )
            savings_acc = uow.ledger.ensure_account(
                account_type=AccountType.SAVINGS_LIABILITY,
                currency=wallet.currency,
                owner_ref=str(wallet.user_id),
            )
            txn = LedgerTransaction.vault_move(
                id=txn_id,
                occurred_at=now,
                reference=f"VLT-{txn_id}",
                client_account_id=client_acc,
                savings_account_id=savings_acc,
                wallet_id=EntityId(str(wallet.id)),
                pocket_ref=str(pocket.id),
                amount=amount,
                into_vault=self._into_vault,
                metadata={
                    "into_vault": self._into_vault,
                    "amount_minor": amount.amount_minor,
                    "pocket_name": pocket.name,
                },
            )

            if self._into_vault:
                wallet.move_to_vault(amount, now)  # lève InsufficientFunds / WalletFrozen
                vault.deposit(pocket_id=pocket.id, amount=amount, now=now)
            else:
                vault.withdraw(pocket_id=pocket.id, amount=amount, now=now)  # lève PocketLocked
                wallet.move_from_vault(amount, now)

            uow.ledger.add(txn)
            uow.wallets.save(wallet)
            uow.vaults.save(vault)
            captured.update(
                pocket_id=str(pocket.id),
                pocket_name=pocket.name,
                currency=wallet.currency.code,
                available_after=wallet.available.amount_minor,
                pocket_after=vault.pocket(pocket.id).balance.amount_minor,
                vaulted_after=vault.total.amount_minor,
            )

        execute_in_uow(self._services.uow, self._services.events, work)
        receipt = VaultMoveReceipt(
            pocket_id=captured["pocket_id"],
            pocket_name=captured["pocket_name"],
            direction="in" if self._into_vault else "out",
            amount_minor=amount_minor,
            currency=captured["currency"],
            wallet_available_after_minor=captured["available_after"],
            pocket_balance_after_minor=captured["pocket_after"],
            vaulted_after_minor=captured["vaulted_after"],
            occurred_at=now.isoformat(),
        )
        return receipt, receipt.to_dict()


class MoveToVault(UseCase[MoveToVaultCommand, VaultMoveReceipt]):
    def __init__(self, *, services: AppServices) -> None:
        self._impl = _VaultMove(services=services, into_vault=True)

    def execute(self, command: MoveToVaultCommand) -> VaultMoveReceipt:
        return self._impl.run(
            user_id=command.user_id,
            pocket_id=command.pocket_id,
            amount_minor=command.amount_minor,
            idempotency_key=command.idempotency_key,
        )


class MoveFromVault(UseCase[MoveFromVaultCommand, VaultMoveReceipt]):
    def __init__(self, *, services: AppServices) -> None:
        self._impl = _VaultMove(services=services, into_vault=False)

    def execute(self, command: MoveFromVaultCommand) -> VaultMoveReceipt:
        return self._impl.run(
            user_id=command.user_id,
            pocket_id=command.pocket_id,
            amount_minor=command.amount_minor,
            idempotency_key=command.idempotency_key,
        )


def _require_vault(uow: WorkUnitOfWork, wallet: Any) -> Vault:
    vault = uow.vaults.get_for_wallet(EntityId(str(wallet.id)))
    if vault is None:
        raise InvalidInput("Aucune poche de coffre : ouvrez-en une d'abord.")
    return vault


__all__ = [
    "CloseVaultPocket",
    "CloseVaultPocketCommand",
    "GetVault",
    "GetVaultCommand",
    "MoveFromVault",
    "MoveFromVaultCommand",
    "MoveToVault",
    "MoveToVaultCommand",
    "OpenVaultPocket",
    "OpenVaultPocketCommand",
    "RenameVaultPocket",
    "RenameVaultPocketCommand",
    "VaultMoveReceipt",
    "VaultPocketView",
    "VaultView",
]
