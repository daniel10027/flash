"""Ports du sous-domaine ledger."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime
from typing import Protocol, runtime_checkable

from flash.domain.ledger.account import LedgerAccount
from flash.domain.ledger.chart import AccountType
from flash.domain.ledger.transaction import LedgerTransaction
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import Currency


@runtime_checkable
class LedgerRepository(Protocol):
    """Persistance append-only du grand livre.

    Les transactions sont **immuables** : ``add`` insère, il n'existe ni update ni
    delete. Les corrections passent par une transaction ``REVERSAL``.
    """

    def add(self, transaction: LedgerTransaction) -> None: ...

    def get(self, transaction_id: EntityId) -> LedgerTransaction | None: ...

    def get_by_reference(self, reference: str) -> list[LedgerTransaction]: ...

    def wallet_balance(self, wallet_id: EntityId) -> int:
        """Solde théorique du portefeuille recalculé depuis le ledger : somme des
        crédits moins somme des débits des postings portant ce ``wallet_id`` (unité
        mineure). Doit égaler ``available + reserved`` de la projection."""
        ...

    def list_for_wallet(
        self, wallet_id: EntityId, *, limit: int = 50, before: EntityId | None = None
    ) -> Iterable[LedgerTransaction]: ...

    def list_for_wallets(
        self, wallet_ids: list[EntityId], *, limit: int = 50, before: EntityId | None = None
    ) -> list[LedgerTransaction]:
        """Transactions touchant l'un des portefeuilles, les plus récentes d'abord.

        ``before`` (id UUIDv7) pagine : renvoie ce qui est strictement antérieur.
        """
        ...

    def list_since(
        self, since: datetime, *, limit: int = 5_000
    ) -> list[LedgerTransaction]:
        """Toutes les transactions dont ``occurred_at`` ≥ ``since`` (analyse AML, exports)."""
        ...

    def list_between(
        self, start: datetime, end: datetime, *, limit: int = 100_000
    ) -> list[LedgerTransaction]:
        """Transactions dont ``occurred_at`` ∈ ``[start, end)`` — ordre chronologique
        croissant (journal comptable, exports réglementaires)."""
        ...

    def list_accounts(self) -> list[LedgerAccount]:
        """Tous les comptes du plan (balance générale)."""
        ...

    def ensure_account(
        self,
        *,
        account_type: AccountType,
        currency: Currency,
        owner_ref: str | None = None,
    ) -> EntityId:
        """Retourne l'id du compte (type, propriétaire, devise), le créant au besoin.

        Sert à résoudre aussi bien les comptes système (``FLASH_FEE_INCOME`` →
        ``owner_ref=None``) que les comptes rattachés à un tiers (``CLIENT_LIABILITY``
        d'un utilisateur, ``AGENT_FLOAT`` d'un agent…).
        """
        ...


__all__ = ["LedgerRepository"]
