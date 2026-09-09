"""Agrégat ``Vault`` — le coffre d'un portefeuille : des **poches** verrouillables où
l'utilisateur met de l'argent de côté.

Le coffre ne « détient » pas de valeur en propre : chaque mouvement de poche est le
reflet d'un ``Wallet.move_to_vault`` / ``move_from_vault`` **dans la même Unit of Work**
(et d'une ``LedgerTransaction.vault_move``). Invariant vérifiable :
``sum(pocket.balance) == wallet.vaulted``.

Une poche peut être *verrouillée jusqu'à une date* : aucun retrait avant l'échéance
(``PocketLocked``). Elle ne peut être supprimée que vide (``PocketNotEmpty``).
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from flash.domain.shared.errors import InvalidInput, PocketLocked, PocketNotEmpty
from flash.domain.shared.events import EventRecorder
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import Currency, Money
from flash.domain.vault.events import (
    VaultPocketClosed,
    VaultPocketDeposited,
    VaultPocketOpened,
    VaultPocketRenamed,
    VaultPocketWithdrawn,
)

_MAX_NAME = 60


class VaultPocket:
    """Une poche du coffre : un nom, un solde, un objectif et une échéance optionnels."""

    def __init__(
        self,
        *,
        id: EntityId,
        name: str,
        balance: Money,
        created_at: datetime,
        goal_minor: int | None = None,
        locked_until: datetime | None = None,
    ) -> None:
        if not name.strip():
            raise InvalidInput("Le nom de la poche est requis.")
        if goal_minor is not None and goal_minor <= 0:
            raise InvalidInput("L'objectif doit être strictement positif.")
        if balance.is_negative:
            raise ValueError("Le solde d'une poche ne peut pas être négatif.")
        self.id = id
        self.name = name.strip()[:_MAX_NAME]
        self.balance = balance
        self.created_at = created_at
        self.goal_minor = goal_minor
        self.locked_until = locked_until

    def is_locked(self, now: datetime) -> bool:
        return self.locked_until is not None and now < self.locked_until

    @property
    def is_empty(self) -> bool:
        return self.balance.is_zero

    @property
    def progress_bps(self) -> int | None:
        """Avancement vers l'objectif en points de base (10 000 = 100 %)."""
        if self.goal_minor is None or self.goal_minor == 0:
            return None
        return min(10_000, self.balance.amount_minor * 10_000 // self.goal_minor)


class Vault(EventRecorder):
    def __init__(
        self,
        *,
        id: EntityId,
        wallet_id: EntityId,
        user_id: EntityId,
        currency: Currency,
        created_at: datetime,
        pockets: Iterable[VaultPocket] = (),
    ) -> None:
        super().__init__()
        self.id = id
        self.wallet_id = wallet_id
        self.user_id = user_id
        self.currency = currency
        self.created_at = created_at
        self._pockets: dict[str, VaultPocket] = {str(p.id): p for p in pockets}

    @classmethod
    def for_wallet(
        cls,
        *,
        vault_id: EntityId,
        wallet_id: EntityId,
        user_id: EntityId,
        currency: Currency,
        now: datetime,
    ) -> Vault:
        return cls(
            id=vault_id,
            wallet_id=wallet_id,
            user_id=user_id,
            currency=currency,
            created_at=now,
        )

    # ------------------------------------------------------------------ lecture
    @property
    def pockets(self) -> list[VaultPocket]:
        return sorted(self._pockets.values(), key=lambda p: p.created_at)

    @property
    def total(self) -> Money:
        out = Money.zero(self.currency)
        for pocket in self._pockets.values():
            out = out + pocket.balance
        return out

    def pocket(self, pocket_id: EntityId) -> VaultPocket:
        found = self._pockets.get(str(pocket_id))
        if found is None:
            raise InvalidInput("Poche de coffre introuvable.")
        return found

    # --------------------------------------------------------------- mutations
    def open_pocket(
        self,
        *,
        pocket_id: EntityId,
        name: str,
        now: datetime,
        goal_minor: int | None = None,
        locked_until: datetime | None = None,
    ) -> VaultPocket:
        if locked_until is not None and locked_until <= now:
            raise InvalidInput("La date de verrouillage doit être dans le futur.")
        pocket = VaultPocket(
            id=pocket_id,
            name=name,
            balance=Money.zero(self.currency),
            created_at=now,
            goal_minor=goal_minor,
            locked_until=locked_until,
        )
        self._pockets[str(pocket_id)] = pocket
        self.record_event(
            VaultPocketOpened(
                occurred_at=now,
                aggregate_id=str(self.id),
                user_id=str(self.user_id),
                wallet_id=str(self.wallet_id),
                pocket_id=str(pocket_id),
                pocket_name=pocket.name,
                goal_minor=goal_minor,
                locked_until=locked_until.isoformat() if locked_until else None,
            )
        )
        return pocket

    def deposit(self, *, pocket_id: EntityId, amount: Money, now: datetime) -> None:
        self._guard_amount(amount)
        pocket = self.pocket(pocket_id)
        pocket.balance = pocket.balance + amount
        self.record_event(
            VaultPocketDeposited(
                occurred_at=now,
                aggregate_id=str(self.id),
                user_id=str(self.user_id),
                wallet_id=str(self.wallet_id),
                pocket_id=str(pocket_id),
                pocket_name=pocket.name,
                amount_minor=amount.amount_minor,
                currency=self.currency.code,
            )
        )

    def withdraw(self, *, pocket_id: EntityId, amount: Money, now: datetime) -> None:
        self._guard_amount(amount)
        pocket = self.pocket(pocket_id)
        if pocket.is_locked(now):
            raise PocketLocked(
                pocket=str(pocket_id),
                locked_until=pocket.locked_until.isoformat() if pocket.locked_until else None,
            )
        if pocket.balance < amount:
            raise InvalidInput("Solde de la poche insuffisant.")
        pocket.balance = pocket.balance - amount
        self.record_event(
            VaultPocketWithdrawn(
                occurred_at=now,
                aggregate_id=str(self.id),
                user_id=str(self.user_id),
                wallet_id=str(self.wallet_id),
                pocket_id=str(pocket_id),
                pocket_name=pocket.name,
                amount_minor=amount.amount_minor,
                currency=self.currency.code,
            )
        )

    def rename_pocket(self, *, pocket_id: EntityId, name: str, now: datetime) -> None:
        if not name.strip():
            raise InvalidInput("Le nom de la poche est requis.")
        pocket = self.pocket(pocket_id)
        pocket.name = name.strip()[:_MAX_NAME]
        self.record_event(
            VaultPocketRenamed(
                occurred_at=now,
                aggregate_id=str(self.id),
                pocket_id=str(pocket_id),
                pocket_name=pocket.name,
            )
        )

    def close_pocket(self, *, pocket_id: EntityId, now: datetime) -> None:
        pocket = self.pocket(pocket_id)
        if not pocket.is_empty:
            raise PocketNotEmpty(pocket=str(pocket_id))
        del self._pockets[str(pocket_id)]
        self.record_event(
            VaultPocketClosed(
                occurred_at=now,
                aggregate_id=str(self.id),
                user_id=str(self.user_id),
                wallet_id=str(self.wallet_id),
                pocket_id=str(pocket_id),
            )
        )

    def _guard_amount(self, amount: Money) -> None:
        if amount.currency != self.currency:
            raise InvalidInput("Devise du montant différente de celle du coffre.")
        if not amount.is_positive:
            raise InvalidInput("Le montant doit être strictement positif.")

    def __repr__(self) -> str:
        return f"Vault(wallet={self.wallet_id!s}, pockets={len(self._pockets)}, total={self.total})"


__all__ = ["Vault", "VaultPocket"]
