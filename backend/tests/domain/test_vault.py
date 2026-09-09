"""Tests de l'agrégat ``Vault`` (BE-047) : poches, verrouillage, invariants."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from flash.domain.shared.errors import InvalidInput, PocketLocked, PocketNotEmpty
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import XOF, Currency, Money
from flash.domain.vault.vault import Vault, VaultPocket

T0 = datetime(2026, 1, 1, tzinfo=UTC)
VAULT_ID = EntityId(UUID(int=1))
WALLET_ID = EntityId(UUID(int=2))
USER_ID = EntityId(UUID(int=3))
P1 = EntityId(UUID(int=10))
P2 = EntityId(UUID(int=11))


def xof(n: int) -> Money:
    return Money(n, XOF)


def new_vault() -> Vault:
    return Vault.for_wallet(
        vault_id=VAULT_ID, wallet_id=WALLET_ID, user_id=USER_ID, currency=XOF, now=T0
    )


class TestOpenPocket:
    def test_open_pocket_starts_empty_and_records_event(self) -> None:
        v = new_vault()
        pocket = v.open_pocket(pocket_id=P1, name="Vacances", now=T0)
        assert pocket.balance == xof(0)
        assert pocket.is_empty
        assert v.total == xof(0)
        assert [e.name for e in v.pull_events()] == ["VaultPocketOpened"]

    def test_open_pocket_trims_and_caps_name(self) -> None:
        v = new_vault()
        pocket = v.open_pocket(pocket_id=P1, name="  " + "x" * 80 + "  ", now=T0)
        assert len(pocket.name) == 60

    def test_open_pocket_blank_name_rejected(self) -> None:
        v = new_vault()
        with pytest.raises(InvalidInput, match="nom de la poche"):
            v.open_pocket(pocket_id=P1, name="   ", now=T0)

    def test_open_pocket_non_positive_goal_rejected(self) -> None:
        v = new_vault()
        with pytest.raises(InvalidInput, match="objectif"):
            v.open_pocket(pocket_id=P1, name="X", now=T0, goal_minor=0)

    def test_open_pocket_past_lock_date_rejected(self) -> None:
        v = new_vault()
        with pytest.raises(InvalidInput, match="futur"):
            v.open_pocket(pocket_id=P1, name="X", now=T0, locked_until=T0 - timedelta(days=1))

    def test_open_pocket_with_future_lock_ok(self) -> None:
        v = new_vault()
        until = T0 + timedelta(days=30)
        pocket = v.open_pocket(pocket_id=P1, name="Bloqué", now=T0, locked_until=until)
        assert pocket.is_locked(T0) is True
        assert pocket.is_locked(until + timedelta(seconds=1)) is False


class TestDepositWithdraw:
    def test_deposit_then_withdraw_updates_pocket_and_total(self) -> None:
        v = new_vault()
        v.open_pocket(pocket_id=P1, name="Vacances", now=T0)
        v.pull_events()

        v.deposit(pocket_id=P1, amount=xof(20_000), now=T0)
        assert v.pocket(P1).balance == xof(20_000)
        assert v.total == xof(20_000)
        assert [e.name for e in v.pull_events()] == ["VaultPocketDeposited"]

        v.withdraw(pocket_id=P1, amount=xof(5_000), now=T0)
        assert v.pocket(P1).balance == xof(15_000)
        assert [e.name for e in v.pull_events()] == ["VaultPocketWithdrawn"]

    def test_total_sums_every_pocket(self) -> None:
        v = new_vault()
        v.open_pocket(pocket_id=P1, name="A", now=T0)
        v.open_pocket(pocket_id=P2, name="B", now=T0 + timedelta(seconds=1))
        v.deposit(pocket_id=P1, amount=xof(1_000), now=T0)
        v.deposit(pocket_id=P2, amount=xof(2_500), now=T0)
        assert v.total == xof(3_500)
        assert [p.name for p in v.pockets] == ["A", "B"]  # trié par created_at

    def test_withdraw_more_than_pocket_balance_rejected(self) -> None:
        v = new_vault()
        v.open_pocket(pocket_id=P1, name="A", now=T0)
        v.deposit(pocket_id=P1, amount=xof(1_000), now=T0)
        with pytest.raises(InvalidInput, match="insuffisant"):
            v.withdraw(pocket_id=P1, amount=xof(1_001), now=T0)

    def test_withdraw_locked_pocket_rejected(self) -> None:
        v = new_vault()
        until = T0 + timedelta(days=10)
        v.open_pocket(pocket_id=P1, name="Bloqué", now=T0, locked_until=until)
        v.deposit(pocket_id=P1, amount=xof(1_000), now=T0)
        with pytest.raises(PocketLocked) as exc:
            v.withdraw(pocket_id=P1, amount=xof(500), now=T0 + timedelta(days=1))
        assert exc.value.details["locked_until"] == until.isoformat()

    def test_withdraw_after_lock_expiry_ok(self) -> None:
        v = new_vault()
        until = T0 + timedelta(days=10)
        v.open_pocket(pocket_id=P1, name="Bloqué", now=T0, locked_until=until)
        v.deposit(pocket_id=P1, amount=xof(1_000), now=T0)
        v.withdraw(pocket_id=P1, amount=xof(1_000), now=until + timedelta(seconds=1))
        assert v.pocket(P1).is_empty

    @pytest.mark.parametrize("bad", [0, -10])
    def test_non_positive_amount_rejected(self, bad: int) -> None:
        v = new_vault()
        v.open_pocket(pocket_id=P1, name="A", now=T0)
        with pytest.raises(InvalidInput, match="strictement positif"):
            v.deposit(pocket_id=P1, amount=xof(bad), now=T0)

    def test_wrong_currency_rejected(self) -> None:
        v = new_vault()
        v.open_pocket(pocket_id=P1, name="A", now=T0)
        with pytest.raises(InvalidInput, match=r"[Dd]evise"):
            v.deposit(pocket_id=P1, amount=Money(10, Currency.of("EUR")), now=T0)

    def test_unknown_pocket_rejected(self) -> None:
        v = new_vault()
        with pytest.raises(InvalidInput, match="introuvable"):
            v.deposit(pocket_id=P2, amount=xof(1), now=T0)


class TestRenameAndClose:
    def test_rename_pocket(self) -> None:
        v = new_vault()
        v.open_pocket(pocket_id=P1, name="A", now=T0)
        v.pull_events()
        v.rename_pocket(pocket_id=P1, name="Voyage 2027", now=T0)
        assert v.pocket(P1).name == "Voyage 2027"
        assert [e.name for e in v.pull_events()] == ["VaultPocketRenamed"]

    def test_rename_blank_rejected(self) -> None:
        v = new_vault()
        v.open_pocket(pocket_id=P1, name="A", now=T0)
        with pytest.raises(InvalidInput, match="nom de la poche"):
            v.rename_pocket(pocket_id=P1, name="  ", now=T0)

    def test_close_empty_pocket(self) -> None:
        v = new_vault()
        v.open_pocket(pocket_id=P1, name="A", now=T0)
        v.pull_events()
        v.close_pocket(pocket_id=P1, now=T0)
        assert v.pockets == []
        assert [e.name for e in v.pull_events()] == ["VaultPocketClosed"]

    def test_close_non_empty_pocket_rejected(self) -> None:
        v = new_vault()
        v.open_pocket(pocket_id=P1, name="A", now=T0)
        v.deposit(pocket_id=P1, amount=xof(1), now=T0)
        with pytest.raises(PocketNotEmpty):
            v.close_pocket(pocket_id=P1, now=T0)


class TestPocketValueObject:
    def test_reconstruction_rejects_negative_balance(self) -> None:
        with pytest.raises(ValueError, match="négatif"):
            VaultPocket(id=P1, name="A", balance=xof(-1), created_at=T0)

    def test_progress_bps(self) -> None:
        p = VaultPocket(id=P1, name="A", balance=xof(2_500), created_at=T0, goal_minor=10_000)
        assert p.progress_bps == 2_500
        capped = VaultPocket(id=P1, name="A", balance=xof(20_000), created_at=T0, goal_minor=10_000)
        assert capped.progress_bps == 10_000
        assert VaultPocket(id=P1, name="A", balance=xof(1), created_at=T0).progress_bps is None

    def test_repr_mentions_total(self) -> None:
        v = new_vault()
        v.open_pocket(pocket_id=P1, name="A", now=T0)
        v.deposit(pocket_id=P1, amount=xof(700), now=T0)
        assert "700" in repr(v)


def test_reconstructed_vault_exposes_pockets() -> None:
    pockets = [
        VaultPocket(id=P1, name="A", balance=xof(1_000), created_at=T0),
        VaultPocket(id=P2, name="B", balance=xof(500), created_at=T0 + timedelta(seconds=1)),
    ]
    v = Vault(
        id=VAULT_ID,
        wallet_id=WALLET_ID,
        user_id=USER_ID,
        currency=XOF,
        created_at=T0,
        pockets=pockets,
    )
    assert v.total == xof(1_500)
    assert [p.name for p in v.pockets] == ["A", "B"]
