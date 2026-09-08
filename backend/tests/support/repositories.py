"""Dépôts et Unit of Work en mémoire pour les tests de la couche application.

Respectent les contrats des ports de ``flash.domain`` sans aucune I/O. Le suivi des
agrégats manipulés permet à ``InMemoryUnitOfWork.collect_new_events`` de récupérer les
événements après un cas d'usage.
"""

from __future__ import annotations

from collections.abc import Iterable

from flash.domain.identity.user import User
from flash.domain.ledger.chart import AccountType
from flash.domain.ledger.transaction import LedgerTransaction
from flash.domain.shared.errors import PhoneNumberAlreadyLinked
from flash.domain.shared.events import DomainEvent, EventRecorder
from flash.domain.shared.identifiers import EntityId, Msisdn
from flash.domain.shared.money import Currency
from flash.domain.wallet.wallet import Wallet


class _Tracking:
    """Mémorise les agrégats touchés pour la collecte d'événements."""

    def __init__(self) -> None:
        self.seen: list[EventRecorder] = []

    def _track(self, aggregate: EventRecorder) -> None:
        if aggregate not in self.seen:
            self.seen.append(aggregate)


class InMemoryUserRepository(_Tracking):
    def __init__(self) -> None:
        super().__init__()
        self._by_id: dict[str, User] = {}

    def get(self, user_id: EntityId) -> User | None:
        user = self._by_id.get(str(user_id))
        if user is not None:
            self._track(user)
        return user

    def get_by_msisdn(self, msisdn: Msisdn) -> User | None:
        for user in self._by_id.values():
            if msisdn in user.msisdns:
                self._track(user)
                return user
        return None

    def exists_with_msisdn(self, msisdn: Msisdn) -> bool:
        return any(msisdn in u.msisdns for u in self._by_id.values())

    def _assert_msisdns_free(self, user: User) -> None:
        for other_id, other in self._by_id.items():
            if other_id == str(user.id):
                continue
            if user.msisdns & other.msisdns:
                raise PhoneNumberAlreadyLinked()

    def add(self, user: User) -> None:
        self._assert_msisdns_free(user)
        self._by_id[str(user.id)] = user
        self._track(user)

    def save(self, user: User) -> None:
        self._assert_msisdns_free(user)
        self._by_id[str(user.id)] = user
        self._track(user)


class InMemoryWalletRepository(_Tracking):
    def __init__(self) -> None:
        super().__init__()
        self._by_id: dict[str, Wallet] = {}

    def get(self, wallet_id: EntityId) -> Wallet | None:
        wallet = self._by_id.get(str(wallet_id))
        if wallet is not None:
            self._track(wallet)
        return wallet

    def get_for_user(self, user_id: EntityId, currency: Currency) -> Wallet | None:
        for wallet in self._by_id.values():
            if wallet.user_id == user_id and wallet.currency == currency:
                self._track(wallet)
                return wallet
        return None

    def list_for_user(self, user_id: EntityId) -> list[Wallet]:
        found = [w for w in self._by_id.values() if w.user_id == user_id]
        for wallet in found:
            self._track(wallet)
        return found

    def get_for_update(self, wallet_id: EntityId) -> Wallet:
        wallet = self._by_id.get(str(wallet_id))
        if wallet is None:
            raise KeyError(wallet_id)
        self._track(wallet)
        return wallet

    def add(self, wallet: Wallet) -> None:
        self._by_id[str(wallet.id)] = wallet
        self._track(wallet)

    def save(self, wallet: Wallet) -> None:
        self._by_id[str(wallet.id)] = wallet
        self._track(wallet)


class InMemoryLedgerRepository:
    def __init__(self) -> None:
        self._by_id: dict[str, LedgerTransaction] = {}
        self._accounts: dict[tuple[str, str, str | None], EntityId] = {}
        self._account_seq = 0

    def add(self, transaction: LedgerTransaction) -> None:
        self._by_id[str(transaction.id)] = transaction

    def get(self, transaction_id: EntityId) -> LedgerTransaction | None:
        return self._by_id.get(str(transaction_id))

    def get_by_reference(self, reference: str) -> list[LedgerTransaction]:
        return [t for t in self._by_id.values() if t.reference == reference]

    def list_for_wallet(
        self, wallet_id: EntityId, *, limit: int = 50, before: EntityId | None = None
    ) -> Iterable[LedgerTransaction]:
        matched = [
            t for t in self._by_id.values() if any(p.wallet_id == wallet_id for p in t.postings)
        ]
        return matched[:limit]

    def ensure_account(
        self,
        *,
        account_type: AccountType,
        currency: Currency,
        owner_ref: str | None = None,
    ) -> EntityId:
        key = (account_type.value, currency.code, owner_ref)
        if key not in self._accounts:
            self._account_seq += 1
            self._accounts[key] = EntityId(f"{self._account_seq:08d}-0000-0000-0000-000000000000")
        return self._accounts[key]

    @property
    def transactions(self) -> list[LedgerTransaction]:
        return list(self._by_id.values())


class InMemoryUnitOfWork:
    """Frontière transactionnelle en mémoire."""

    def __init__(
        self,
        *,
        users: InMemoryUserRepository | None = None,
        wallets: InMemoryWalletRepository | None = None,
        ledger: InMemoryLedgerRepository | None = None,
    ) -> None:
        self.users = users or InMemoryUserRepository()
        self.wallets = wallets or InMemoryWalletRepository()
        self.ledger = ledger or InMemoryLedgerRepository()
        self.committed = False
        self.rolled_back = False

    def __enter__(self) -> InMemoryUnitOfWork:
        self.committed = False
        self.rolled_back = False
        return self

    def __exit__(self, exc_type: object, exc: object, tb: object) -> None:
        if exc_type is not None and not self.committed:
            self.rollback()

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    def collect_new_events(self) -> list[DomainEvent]:
        events: list[DomainEvent] = []
        for aggregate in (*self.users.seen, *self.wallets.seen):
            events.extend(aggregate.pull_events())
        return events


__all__ = [
    "InMemoryLedgerRepository",
    "InMemoryUnitOfWork",
    "InMemoryUserRepository",
    "InMemoryWalletRepository",
]
