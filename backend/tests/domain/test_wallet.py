"""Tests de l'agrégat Wallet (BE-009)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

import pytest

from flash.domain.shared.errors import InsufficientFunds, InvalidReservation, WalletFrozen
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import XOF, Money
from flash.domain.wallet.wallet import Wallet, WalletStatus

T0 = datetime(2026, 1, 1, tzinfo=UTC)
WID = EntityId(UUID(int=10))
UID = EntityId(UUID(int=1))


def xof(n: int) -> Money:
    return Money(n, XOF)


def new_wallet(balance: int = 0) -> Wallet:
    w = Wallet.open(wallet_id=WID, user_id=UID, currency=XOF, now=T0)
    w.pull_events()
    if balance:
        w.credit(xof(balance), T0)
        w.pull_events()
    return w


class TestOpen:
    def test_open_starts_empty_and_active(self) -> None:
        w = Wallet.open(wallet_id=WID, user_id=UID, currency=XOF, now=T0)
        assert w.available == xof(0)
        assert w.reserved == xof(0)
        assert w.balance == xof(0)
        assert w.is_active
        assert [e.name for e in w.pull_events()] == ["WalletOpened"]

    def test_reconstruction_rejects_wrong_currency(self) -> None:
        from flash.domain.shared.money import Currency

        with pytest.raises(ValueError, match="devise"):
            Wallet(
                id=WID,
                user_id=UID,
                currency=XOF,
                available=Money(0, Currency.of("EUR")),
                reserved=xof(0),
            )

    def test_reconstruction_rejects_negative(self) -> None:
        with pytest.raises(ValueError, match="négatif"):
            Wallet(id=WID, user_id=UID, currency=XOF, available=xof(-1), reserved=xof(0))


class TestCreditDebit:
    def test_credit_increases_available(self) -> None:
        w = new_wallet()
        w.credit(xof(10_000), T0)
        assert w.available == xof(10_000)
        assert [e.name for e in w.pull_events()] == ["WalletCredited"]

    def test_debit_decreases_available(self) -> None:
        w = new_wallet(10_000)
        w.debit(xof(4_000), T0)
        assert w.available == xof(6_000)
        assert [e.name for e in w.pull_events()] == ["WalletDebited"]

    def test_debit_more_than_available_rejected(self) -> None:
        w = new_wallet(1_000)
        with pytest.raises(InsufficientFunds) as exc:
            w.debit(xof(1_001), T0)
        assert exc.value.details == {"available": 1_000, "requested": 1_001}
        assert w.available == xof(1_000)

    @pytest.mark.parametrize("bad", [0, -5])
    def test_non_positive_amount_rejected(self, bad: int) -> None:
        w = new_wallet(1_000)
        with pytest.raises(ValueError, match="strictement positif"):
            w.credit(xof(bad), T0)

    def test_wrong_currency_amount_rejected(self) -> None:
        from flash.domain.shared.money import Currency

        w = new_wallet(1_000)
        with pytest.raises(ValueError, match="Devise"):
            w.debit(Money(10, Currency.of("EUR")), T0)


class TestReservations:
    def test_reserve_moves_available_to_reserved(self) -> None:
        w = new_wallet(10_000)
        w.reserve(xof(3_000), T0)
        assert w.available == xof(7_000)
        assert w.reserved == xof(3_000)
        assert w.balance == xof(10_000)
        assert [e.name for e in w.pull_events()] == ["FundsReserved"]

    def test_reserve_more_than_available_rejected(self) -> None:
        w = new_wallet(2_000)
        with pytest.raises(InsufficientFunds):
            w.reserve(xof(2_500), T0)

    def test_release_returns_reserved_to_available(self) -> None:
        w = new_wallet(10_000)
        w.reserve(xof(3_000), T0)
        w.pull_events()
        w.release(xof(3_000), T0)
        assert w.available == xof(10_000)
        assert w.reserved == xof(0)
        assert [e.name for e in w.pull_events()] == ["FundsReleased"]

    def test_settle_reservation_removes_value_from_wallet(self) -> None:
        w = new_wallet(10_000)
        w.reserve(xof(3_000), T0)
        w.pull_events()
        w.settle_reservation(xof(3_000), T0)
        assert w.available == xof(7_000)
        assert w.reserved == xof(0)
        assert w.balance == xof(7_000)
        assert [e.name for e in w.pull_events()] == ["ReservationSettled"]

    @pytest.mark.parametrize("method", ["release", "settle_reservation"])
    def test_release_or_settle_more_than_reserved_rejected(self, method: str) -> None:
        w = new_wallet(10_000)
        w.reserve(xof(1_000), T0)
        with pytest.raises(InvalidReservation):
            getattr(w, method)(xof(1_500), T0)


class TestFreeze:
    def test_frozen_wallet_blocks_debit_and_reserve(self) -> None:
        w = new_wallet(10_000)
        w.freeze("enquête", T0)
        assert w.status is WalletStatus.FROZEN
        with pytest.raises(WalletFrozen):
            w.debit(xof(100), T0)
        with pytest.raises(WalletFrozen):
            w.reserve(xof(100), T0)

    def test_frozen_wallet_still_accepts_credit(self) -> None:
        w = new_wallet()
        w.freeze("x", T0)
        w.credit(xof(500), T0)  # on peut toujours créditer un wallet gelé
        assert w.available == xof(500)

    def test_freeze_unfreeze_idempotent(self) -> None:
        w = new_wallet()
        w.freeze("x", T0)
        w.pull_events()
        w.freeze("x", T0)
        assert w.pull_events() == []
        w.unfreeze(T0)
        assert [e.name for e in w.pull_events()] == ["WalletUnfrozen"]
        w.unfreeze(T0)
        assert w.pull_events() == []

    def test_repr_is_informative(self) -> None:
        r = repr(new_wallet(2_500))
        assert "XOF" in r and "2500" in r
