"""Agrégat ``Wallet`` — solde d'un utilisateur dans une devise.

Le solde est la **projection** du ledger : ces méthodes sont appelées par les cas
d'usage dans la même transaction qu'une ``LedgerTransaction`` équilibrée. Elles ne
« créent » pas de valeur, elles reflètent le mouvement comptable.

- ``available`` : fonds utilisables immédiatement.
- ``reserved`` : fonds bloqués (retrait cash en attente de code, autorisation carte…).
- ``vaulted`` : fonds rangés dans une poche de coffre (BE-047).
- ``saved`` : fonds engagés dans un plan d'épargne (BE-050), intérêts compris.
- ``balance`` : ``available + reserved + vaulted + saved`` (dette totale de Flash envers
  le client).

Invariants : chaque poste ``>= 0``, tout montant dans la devise du portefeuille et
strictement positif.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum

from flash.domain.shared.errors import (
    InsufficientFunds,
    InvalidReservation,
)
from flash.domain.shared.errors import (
    WalletFrozen as WalletFrozenError,
)
from flash.domain.shared.events import EventRecorder
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import Currency, Money
from flash.domain.wallet.events import (
    FundsReleased,
    FundsReserved,
    FundsSaved,
    FundsUnsaved,
    FundsUnvaulted,
    FundsVaulted,
    ReservationSettled,
    SavingsInterestCredited,
    WalletCredited,
    WalletDebited,
    WalletFrozen,
    WalletOpened,
    WalletUnfrozen,
)


class WalletStatus(StrEnum):
    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"


class Wallet(EventRecorder):
    def __init__(
        self,
        *,
        id: EntityId,
        user_id: EntityId,
        currency: Currency,
        available: Money,
        reserved: Money,
        created_at: datetime,
        vaulted: Money | None = None,
        saved: Money | None = None,
        status: WalletStatus = WalletStatus.ACTIVE,
    ) -> None:
        super().__init__()
        vaulted = vaulted if vaulted is not None else Money.zero(currency)
        saved = saved if saved is not None else Money.zero(currency)
        for label, money in (
            ("available", available),
            ("reserved", reserved),
            ("vaulted", vaulted),
            ("saved", saved),
        ):
            if money.currency != currency:
                raise ValueError(f"{label} n'est pas dans la devise du portefeuille ({currency}).")
            if money.is_negative:
                raise ValueError(f"{label} ne peut pas être négatif.")
        self.id = id
        self.user_id = user_id
        self.currency = currency
        self.available = available
        self.reserved = reserved
        self.vaulted = vaulted
        self.saved = saved
        self.created_at = created_at
        self.status = status

    # ---------------------------------------------------------------- fabrique
    @classmethod
    def open(
        cls, *, wallet_id: EntityId, user_id: EntityId, currency: Currency, now: datetime
    ) -> Wallet:
        wallet = cls(
            id=wallet_id,
            user_id=user_id,
            currency=currency,
            available=Money.zero(currency),
            reserved=Money.zero(currency),
            created_at=now,
        )
        wallet.record_event(
            WalletOpened(
                occurred_at=now,
                aggregate_id=str(wallet_id),
                user_id=str(user_id),
                currency=currency.code,
            )
        )
        return wallet

    # ---------------------------------------------------------------- lecture
    @property
    def balance(self) -> Money:
        return self.available + self.reserved + self.vaulted + self.saved

    @property
    def is_active(self) -> bool:
        return self.status is WalletStatus.ACTIVE

    # --------------------------------------------------------------- garde-fous
    def _guard(self, amount: Money) -> None:
        if amount.currency != self.currency:
            raise ValueError("Devise du montant différente de celle du portefeuille.")
        if not amount.is_positive:
            raise ValueError("Le montant doit être strictement positif.")

    def ensure_active(self) -> None:
        if self.status is not WalletStatus.ACTIVE:
            raise WalletFrozenError()

    # ------------------------------------------------------------- mouvements
    def credit(self, amount: Money, now: datetime) -> None:
        self._guard(amount)
        self.available = self.available + amount
        self.record_event(
            WalletCredited(
                occurred_at=now,
                aggregate_id=str(self.id),
                amount_minor=amount.amount_minor,
                currency=self.currency.code,
            )
        )

    def debit(self, amount: Money, now: datetime) -> None:
        self._guard(amount)
        self.ensure_active()
        if self.available < amount:
            raise InsufficientFunds(
                available=self.available.amount_minor, requested=amount.amount_minor
            )
        self.available = self.available - amount
        self.record_event(
            WalletDebited(
                occurred_at=now,
                aggregate_id=str(self.id),
                amount_minor=amount.amount_minor,
                currency=self.currency.code,
            )
        )

    def reserve(self, amount: Money, now: datetime) -> None:
        self._guard(amount)
        self.ensure_active()
        if self.available < amount:
            raise InsufficientFunds(
                available=self.available.amount_minor, requested=amount.amount_minor
            )
        self.available = self.available - amount
        self.reserved = self.reserved + amount
        self.record_event(
            FundsReserved(
                occurred_at=now,
                aggregate_id=str(self.id),
                amount_minor=amount.amount_minor,
                currency=self.currency.code,
            )
        )

    def release(self, amount: Money, now: datetime) -> None:
        """Rend une réservation au solde disponible (retrait annulé/expiré)."""
        self._guard(amount)
        if self.reserved < amount:
            raise InvalidReservation(
                reserved=self.reserved.amount_minor, requested=amount.amount_minor
            )
        self.reserved = self.reserved - amount
        self.available = self.available + amount
        self.record_event(
            FundsReleased(
                occurred_at=now,
                aggregate_id=str(self.id),
                amount_minor=amount.amount_minor,
                currency=self.currency.code,
            )
        )

    def settle_reservation(self, amount: Money, now: datetime) -> None:
        """Consomme une réservation : la valeur quitte définitivement le portefeuille."""
        self._guard(amount)
        if self.reserved < amount:
            raise InvalidReservation(
                reserved=self.reserved.amount_minor, requested=amount.amount_minor
            )
        self.reserved = self.reserved - amount
        self.record_event(
            ReservationSettled(
                occurred_at=now,
                aggregate_id=str(self.id),
                amount_minor=amount.amount_minor,
                currency=self.currency.code,
            )
        )

    # ------------------------------------------------------------------ coffre
    def move_to_vault(self, amount: Money, now: datetime) -> None:
        """Met de côté : le disponible baisse, le contenu du coffre monte."""
        self._guard(amount)
        self.ensure_active()
        if self.available < amount:
            raise InsufficientFunds(
                available=self.available.amount_minor, requested=amount.amount_minor
            )
        self.available = self.available - amount
        self.vaulted = self.vaulted + amount
        self.record_event(
            FundsVaulted(
                occurred_at=now,
                aggregate_id=str(self.id),
                amount_minor=amount.amount_minor,
                currency=self.currency.code,
            )
        )

    def move_from_vault(self, amount: Money, now: datetime) -> None:
        """Reprend depuis le coffre : le contenu du coffre baisse, le disponible monte."""
        self._guard(amount)
        if self.vaulted < amount:
            raise InvalidReservation(
                reserved=self.vaulted.amount_minor, requested=amount.amount_minor
            )
        self.vaulted = self.vaulted - amount
        self.available = self.available + amount
        self.record_event(
            FundsUnvaulted(
                occurred_at=now,
                aggregate_id=str(self.id),
                amount_minor=amount.amount_minor,
                currency=self.currency.code,
            )
        )

    # ----------------------------------------------------------------- épargne
    def move_to_savings(self, amount: Money, now: datetime) -> None:
        """Engage des fonds dans un plan d'épargne : le disponible baisse, ``saved`` monte."""
        self._guard(amount)
        self.ensure_active()
        if self.available < amount:
            raise InsufficientFunds(
                available=self.available.amount_minor, requested=amount.amount_minor
            )
        self.available = self.available - amount
        self.saved = self.saved + amount
        self.record_event(
            FundsSaved(
                occurred_at=now,
                aggregate_id=str(self.id),
                amount_minor=amount.amount_minor,
                currency=self.currency.code,
            )
        )

    def move_from_savings(self, amount: Money, now: datetime) -> None:
        """Rapatrie de l'épargne vers le disponible (retrait partiel ou clôture)."""
        self._guard(amount)
        if self.saved < amount:
            raise InvalidReservation(
                reserved=self.saved.amount_minor, requested=amount.amount_minor
            )
        self.saved = self.saved - amount
        self.available = self.available + amount
        self.record_event(
            FundsUnsaved(
                occurred_at=now,
                aggregate_id=str(self.id),
                amount_minor=amount.amount_minor,
                currency=self.currency.code,
            )
        )

    def add_savings_interest(self, amount: Money, now: datetime) -> None:
        """Capitalise des intérêts : ``saved`` monte, sans toucher au disponible."""
        self._guard(amount)
        self.saved = self.saved + amount
        self.record_event(
            SavingsInterestCredited(
                occurred_at=now,
                aggregate_id=str(self.id),
                amount_minor=amount.amount_minor,
                currency=self.currency.code,
            )
        )

    # ---------------------------------------------------------------- statut
    def freeze(self, reason: str, now: datetime) -> None:
        if self.status is WalletStatus.FROZEN:
            return
        self.status = WalletStatus.FROZEN
        self.record_event(WalletFrozen(occurred_at=now, aggregate_id=str(self.id), reason=reason))

    def unfreeze(self, now: datetime) -> None:
        if self.status is WalletStatus.ACTIVE:
            return
        self.status = WalletStatus.ACTIVE
        self.record_event(WalletUnfrozen(occurred_at=now, aggregate_id=str(self.id)))

    def __repr__(self) -> str:
        return (
            f"Wallet(id={self.id!s}, {self.currency.code}, "
            f"available={self.available.amount_minor}, reserved={self.reserved.amount_minor}, "
            f"vaulted={self.vaulted.amount_minor}, saved={self.saved.amount_minor})"
        )


__all__ = ["Wallet", "WalletStatus"]
