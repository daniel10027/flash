"""Tests des cas d'usage du coffre (BE-047 → BE-049)."""

from __future__ import annotations

from uuid import UUID

import pytest

from flash.application.services import AppServices
from flash.application.statement.queries import ListStatement, ListStatementCommand
from flash.application.vault.operations import (
    CloseVaultPocket,
    CloseVaultPocketCommand,
    GetVault,
    GetVaultCommand,
    MoveFromVault,
    MoveFromVaultCommand,
    MoveToVault,
    MoveToVaultCommand,
    OpenVaultPocket,
    OpenVaultPocketCommand,
    RenameVaultPocket,
    RenameVaultPocketCommand,
)
from flash.domain.identity.pin import Pin
from flash.domain.identity.user import User
from flash.domain.ledger.transaction import TransactionKind, sum_postings
from flash.domain.shared.errors import (
    InsufficientFunds,
    InvalidInput,
    PocketLocked,
    PocketNotEmpty,
)
from flash.domain.shared.identifiers import CountryCode, EntityId, Msisdn
from flash.domain.shared.money import XOF, Money
from flash.domain.wallet.wallet import Wallet
from tests.support.fakes import (
    FakePinHasher,
    FixedClock,
    InMemoryIdempotencyStore,
    RecordingEventPublisher,
    SeqIdGenerator,
)
from tests.support.repositories import InMemoryUnitOfWork

CI = CountryCode("CI")
USER_ID = str(UUID(int=1))
MSISDN = "+2250700000001"


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


@pytest.fixture
def clock() -> FixedClock:
    return FixedClock()


@pytest.fixture
def events() -> RecordingEventPublisher:
    return RecordingEventPublisher()


@pytest.fixture
def services(
    uow: InMemoryUnitOfWork, clock: FixedClock, events: RecordingEventPublisher
) -> AppServices:
    return AppServices(
        uow=lambda: uow,
        clock=clock,
        ids=SeqIdGenerator(),
        events=events,
        idempotency=InMemoryIdempotencyStore(),
    )


def _user(uow: InMemoryUnitOfWork, *, balance: int = 0) -> None:
    user = User.register(
        user_id=EntityId(USER_ID),
        country=CI,
        msisdn=Msisdn(MSISDN),
        pin_hash=FakePinHasher().hash(Pin("1397")),
        now=FixedClock().now(),
    )
    user.activate(FixedClock().now())
    user.pull_events()
    uow.users.add(user)
    wallet = Wallet.open(
        wallet_id=EntityId(str(UUID(int=500))),
        user_id=user.id,
        currency=XOF,
        now=FixedClock().now(),
    )
    if balance:
        wallet.credit(Money(balance, XOF), FixedClock().now())
    wallet.pull_events()
    uow.wallets.add(wallet)


def _open(services: AppServices, **kw: object) -> str:
    view = OpenVaultPocket(services=services).execute(
        OpenVaultPocketCommand(user_id=USER_ID, name="Vacances", **kw)  # type: ignore[arg-type]
    )
    return view.pocket_id


class TestOpenPocket:
    def test_open_creates_vault_and_pocket(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        pocket_id = _open(services, goal_minor=500_000)
        view = GetVault(services=services).execute(GetVaultCommand(user_id=USER_ID))
        assert view.vaulted_minor == 0
        assert [p.pocket_id for p in view.pockets] == [pocket_id]
        assert view.pockets[0].goal_minor == 500_000
        payload = view.to_dict()
        assert payload["pockets"][0]["goal_minor"] == 500_000
        assert payload["pockets"][0]["name"] == "Vacances"

    def test_second_pocket_reuses_same_vault(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        _open(services)
        OpenVaultPocket(services=services).execute(
            OpenVaultPocketCommand(user_id=USER_ID, name="Impôts")
        )
        view = GetVault(services=services).execute(GetVaultCommand(user_id=USER_ID))
        assert len(view.pockets) == 2
        vault = uow.vaults.get_for_user(EntityId(USER_ID))
        assert vault is not None and len(vault.pockets) == 2

    def test_get_vault_without_any_pocket_is_empty(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        view = GetVault(services=services).execute(GetVaultCommand(user_id=USER_ID))
        assert view.vaulted_minor == 0 and view.pockets == [] and view.currency == "XOF"

    def test_blank_name_rejected(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        _user(uow)
        with pytest.raises(InvalidInput, match="nom de la poche"):
            OpenVaultPocket(services=services).execute(
                OpenVaultPocketCommand(user_id=USER_ID, name="   ")
            )

    def test_non_positive_goal_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        with pytest.raises(InvalidInput, match="objectif"):
            OpenVaultPocket(services=services).execute(
                OpenVaultPocketCommand(user_id=USER_ID, name="X", goal_minor=0)
            )

    def test_bad_locked_until_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        with pytest.raises(InvalidInput, match="ISO 8601"):
            OpenVaultPocket(services=services).execute(
                OpenVaultPocketCommand(user_id=USER_ID, name="X", locked_until="pas-une-date")
            )

    def test_locked_until_naive_datetime_is_accepted(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        cmd = OpenVaultPocketCommand(
            user_id=USER_ID, name="Bloqué", locked_until="2027-01-01T00:00:00"
        )
        view = OpenVaultPocket(services=services).execute(cmd)
        assert view.locked_until is not None and view.locked_until.endswith("+00:00")


class TestMoves:
    def test_move_to_vault_moves_available_into_pocket(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=100_000)
        pocket_id = _open(services)
        receipt = MoveToVault(services=services).execute(
            MoveToVaultCommand(
                user_id=USER_ID,
                pocket_id=pocket_id,
                amount_minor=30_000,
                idempotency_key="vault-in-0001",
            )
        )
        assert receipt.direction == "in"
        assert receipt.wallet_available_after_minor == 70_000
        assert receipt.pocket_balance_after_minor == 30_000
        assert receipt.vaulted_after_minor == 30_000

        wallet = uow.wallets.get_for_user(EntityId(USER_ID), XOF)
        assert wallet is not None
        assert wallet.available == Money(70_000, XOF)
        assert wallet.vaulted == Money(30_000, XOF)
        assert wallet.balance == Money(100_000, XOF)  # inchangé

        [txn] = uow.ledger.transactions
        assert txn.kind is TransactionKind.VAULT_MOVE
        assert txn.is_balanced and sum_postings(txn.postings) == {"XOF": 0}

    def test_move_to_vault_insufficient_funds_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=1_000)
        pocket_id = _open(services)
        with pytest.raises(InsufficientFunds):
            MoveToVault(services=services).execute(
                MoveToVaultCommand(
                    user_id=USER_ID,
                    pocket_id=pocket_id,
                    amount_minor=5_000,
                    idempotency_key="vault-in-broke",
                )
            )

    def test_move_to_vault_is_idempotent(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=100_000)
        pocket_id = _open(services)
        cmd = MoveToVaultCommand(
            user_id=USER_ID,
            pocket_id=pocket_id,
            amount_minor=30_000,
            idempotency_key="vault-in-rep",
        )
        first = MoveToVault(services=services).execute(cmd)
        second = MoveToVault(services=services).execute(cmd)
        assert first == second
        wallet = uow.wallets.get_for_user(EntityId(USER_ID), XOF)
        assert wallet is not None and wallet.available == Money(70_000, XOF)  # une seule fois

    def test_move_to_vault_bad_idempotency_key_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=100_000)
        pocket_id = _open(services)
        with pytest.raises(InvalidInput):
            MoveToVault(services=services).execute(
                MoveToVaultCommand(
                    user_id=USER_ID, pocket_id=pocket_id, amount_minor=1_000, idempotency_key="x"
                )
            )

    def test_move_to_vault_non_positive_amount_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=100_000)
        pocket_id = _open(services)
        with pytest.raises(InvalidInput, match="strictement positif"):
            MoveToVault(services=services).execute(
                MoveToVaultCommand(
                    user_id=USER_ID,
                    pocket_id=pocket_id,
                    amount_minor=0,
                    idempotency_key="vault-in-zero",
                )
            )

    def test_move_from_vault_returns_value_to_available(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=100_000)
        pocket_id = _open(services)
        MoveToVault(services=services).execute(
            MoveToVaultCommand(
                user_id=USER_ID,
                pocket_id=pocket_id,
                amount_minor=40_000,
                idempotency_key="vault-in-a",
            )
        )
        receipt = MoveFromVault(services=services).execute(
            MoveFromVaultCommand(
                user_id=USER_ID,
                pocket_id=pocket_id,
                amount_minor=15_000,
                idempotency_key="vault-out-a",
            )
        )
        assert receipt.direction == "out"
        assert receipt.wallet_available_after_minor == 75_000
        assert receipt.pocket_balance_after_minor == 25_000
        assert receipt.vaulted_after_minor == 25_000
        for txn in uow.ledger.transactions:
            assert txn.is_balanced

    def test_vault_moves_appear_in_statement(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=100_000)
        pocket_id = _open(services)
        MoveToVault(services=services).execute(
            MoveToVaultCommand(
                user_id=USER_ID,
                pocket_id=pocket_id,
                amount_minor=40_000,
                idempotency_key="vault-in-stmt",
            )
        )
        MoveFromVault(services=services).execute(
            MoveFromVaultCommand(
                user_id=USER_ID,
                pocket_id=pocket_id,
                amount_minor=15_000,
                idempotency_key="vault-out-stmt",
            )
        )
        page = ListStatement(services=services).execute(ListStatementCommand(user_id=USER_ID))
        moves = [line for line in page.lines if line.kind == "VAULT_MOVE"]
        assert {(m.direction, m.amount_minor) for m in moves} == {("out", 40_000), ("in", 15_000)}
        assert all(m.counterparty_masked == "Vacances" and m.fee_minor == 0 for m in moves)

    def test_move_from_vault_locked_pocket_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork, clock: FixedClock
    ) -> None:
        _user(uow, balance=100_000)
        view = OpenVaultPocket(services=services).execute(
            OpenVaultPocketCommand(
                user_id=USER_ID, name="Bloqué", locked_until="2026-06-01T00:00:00+00:00"
            )
        )
        MoveToVault(services=services).execute(
            MoveToVaultCommand(
                user_id=USER_ID,
                pocket_id=view.pocket_id,
                amount_minor=10_000,
                idempotency_key="vault-in-lock",
            )
        )
        with pytest.raises(PocketLocked):
            MoveFromVault(services=services).execute(
                MoveFromVaultCommand(
                    user_id=USER_ID,
                    pocket_id=view.pocket_id,
                    amount_minor=1_000,
                    idempotency_key="vault-out-lock",
                )
            )

    def test_move_from_vault_more_than_pocket_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=100_000)
        pocket_id = _open(services)
        MoveToVault(services=services).execute(
            MoveToVaultCommand(
                user_id=USER_ID,
                pocket_id=pocket_id,
                amount_minor=5_000,
                idempotency_key="vault-in-small",
            )
        )
        with pytest.raises(InvalidInput, match="insuffisant"):
            MoveFromVault(services=services).execute(
                MoveFromVaultCommand(
                    user_id=USER_ID,
                    pocket_id=pocket_id,
                    amount_minor=6_000,
                    idempotency_key="vault-out-big",
                )
            )

    def test_move_before_any_pocket_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=100_000)
        with pytest.raises(InvalidInput, match="Aucune poche"):
            MoveToVault(services=services).execute(
                MoveToVaultCommand(
                    user_id=USER_ID,
                    pocket_id=str(UUID(int=999)),
                    amount_minor=1_000,
                    idempotency_key="vault-in-nopocket",
                )
            )

    def test_move_unknown_pocket_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=100_000)
        _open(services)
        with pytest.raises(InvalidInput, match="introuvable"):
            MoveToVault(services=services).execute(
                MoveToVaultCommand(
                    user_id=USER_ID,
                    pocket_id=str(UUID(int=888)),
                    amount_minor=1_000,
                    idempotency_key="vault-in-unknown",
                )
            )


class TestRenameAndClose:
    def test_rename_pocket(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        _user(uow)
        pocket_id = _open(services)
        view = RenameVaultPocket(services=services).execute(
            RenameVaultPocketCommand(user_id=USER_ID, pocket_id=pocket_id, name="Voyage 2027")
        )
        assert view.name == "Voyage 2027"
        assert view.to_dict()["name"] == "Voyage 2027"

    def test_rename_blank_rejected(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        _user(uow)
        pocket_id = _open(services)
        with pytest.raises(InvalidInput, match="nom de la poche"):
            RenameVaultPocket(services=services).execute(
                RenameVaultPocketCommand(user_id=USER_ID, pocket_id=pocket_id, name="  ")
            )

    def test_close_empty_pocket(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        _user(uow)
        pocket_id = _open(services)
        CloseVaultPocket(services=services).execute(
            CloseVaultPocketCommand(user_id=USER_ID, pocket_id=pocket_id)
        )
        view = GetVault(services=services).execute(GetVaultCommand(user_id=USER_ID))
        assert view.pockets == []

    def test_close_non_empty_pocket_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow, balance=100_000)
        pocket_id = _open(services)
        MoveToVault(services=services).execute(
            MoveToVaultCommand(
                user_id=USER_ID,
                pocket_id=pocket_id,
                amount_minor=1_000,
                idempotency_key="vault-in-close",
            )
        )
        with pytest.raises(PocketNotEmpty):
            CloseVaultPocket(services=services).execute(
                CloseVaultPocketCommand(user_id=USER_ID, pocket_id=pocket_id)
            )

    def test_rename_before_any_pocket_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        with pytest.raises(InvalidInput, match="Aucune poche"):
            RenameVaultPocket(services=services).execute(
                RenameVaultPocketCommand(
                    user_id=USER_ID, pocket_id=str(UUID(int=7)), name="X"
                )
            )
