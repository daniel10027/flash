"""Tests de l'agrégat User (BE-007)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from flash.domain.identity.kyc import KycTier
from flash.domain.identity.user import MAX_PHONE_NUMBERS, PhoneNumber, User, UserStatus
from flash.domain.shared.errors import (
    AccountClosed,
    CannotRemoveLastPhoneNumber,
    CannotRemovePrimaryPhoneNumber,
    InvalidAccountState,
    PhoneNumberAlreadyLinked,
    PhoneNumberLimitReached,
    PhoneNumberNotFound,
    PhoneNumberNotVerified,
    UserFrozen,
)
from flash.domain.shared.identifiers import CountryCode, EntityId, Msisdn

T0 = datetime(2026, 1, 1, tzinfo=UTC)
CI = CountryCode("CI")


def _msisdn(last: str) -> Msisdn:
    return Msisdn(f"+22507000000{last}")


PIN_HASH = "hashed:1397"


def make_user(n: int = 1) -> User:
    return User.register(
        user_id=EntityId(UUID(int=n)),
        country=CI,
        msisdn=_msisdn("01"),
        pin_hash=PIN_HASH,
        now=T0,
    )


def active_user() -> User:
    user = make_user()
    user.activate(T0 + timedelta(minutes=1))
    user.pull_events()
    return user


class TestRegister:
    def test_register_creates_pending_user_with_one_unverified_primary(self) -> None:
        user = make_user()
        assert user.status is UserStatus.PENDING_ACTIVATION
        assert user.kyc_tier is KycTier.TIER_0
        assert len(user.phone_numbers) == 1
        primary = user.primary_phone_number
        assert primary.is_primary and not primary.is_verified
        assert user.country == CI

    def test_register_records_event(self) -> None:
        user = make_user()
        events = user.pull_events()
        assert [e.name for e in events] == ["UserRegistered"]
        assert events[0].to_payload()["primary_msisdn"] == _msisdn("01").value


class TestActivate:
    def test_activate_verifies_primary_and_activates(self) -> None:
        user = make_user()
        user.pull_events()
        user.activate(T0 + timedelta(minutes=1))
        assert user.is_active
        assert user.primary_phone_number.is_verified
        assert [e.name for e in user.pull_events()] == ["PhoneNumberVerified"]

    def test_activate_twice_rejected(self) -> None:
        user = active_user()
        with pytest.raises(InvalidAccountState):
            user.activate(T0)


class TestAddPhoneNumber:
    def test_add_second_number_unverified_not_primary(self) -> None:
        user = active_user()
        user.add_phone_number(_msisdn("02"), T0)
        assert len(user.phone_numbers) == 2
        added = next(p for p in user.phone_numbers if p.msisdn == _msisdn("02"))
        assert not added.is_primary and not added.is_verified
        assert [e.name for e in user.pull_events()] == ["PhoneNumberAdded"]

    def test_cannot_exceed_five_numbers(self) -> None:
        user = active_user()
        for last in ("02", "03", "04", "05"):
            user.add_phone_number(_msisdn(last), T0)
        assert len(user.phone_numbers) == MAX_PHONE_NUMBERS
        with pytest.raises(PhoneNumberLimitReached):
            user.add_phone_number(_msisdn("06"), T0)

    def test_cannot_add_duplicate_number(self) -> None:
        user = active_user()
        with pytest.raises(PhoneNumberAlreadyLinked):
            user.add_phone_number(_msisdn("01"), T0)

    def test_cannot_add_on_frozen_account(self) -> None:
        user = active_user()
        user.freeze("contrôle", T0)
        with pytest.raises(InvalidAccountState):
            user.add_phone_number(_msisdn("02"), T0)


class TestVerifyAndPrimary:
    def test_verify_phone_number_idempotent(self) -> None:
        user = active_user()
        user.add_phone_number(_msisdn("02"), T0)
        user.pull_events()
        user.verify_phone_number(_msisdn("02"), T0)
        assert [e.name for e in user.pull_events()] == ["PhoneNumberVerified"]
        user.verify_phone_number(_msisdn("02"), T0)  # 2e fois : sans effet
        assert user.pull_events() == []

    def test_set_primary_requires_verified_number(self) -> None:
        user = active_user()
        user.add_phone_number(_msisdn("02"), T0)
        with pytest.raises(PhoneNumberNotVerified):
            user.set_primary_phone_number(_msisdn("02"), T0)

    def test_set_primary_switches_flag_and_emits_event(self) -> None:
        user = active_user()
        user.add_phone_number(_msisdn("02"), T0)
        user.verify_phone_number(_msisdn("02"), T0)
        user.pull_events()
        user.set_primary_phone_number(_msisdn("02"), T0)
        assert user.primary_phone_number.msisdn == _msisdn("02")
        assert sum(1 for p in user.phone_numbers if p.is_primary) == 1
        event = user.pull_events()[0]
        assert event.name == "PrimaryPhoneNumberChanged"
        assert event.to_payload() == {
            "occurred_at": T0.isoformat(),
            "aggregate_id": str(EntityId(UUID(int=1))),
            "previous_msisdn": _msisdn("01").value,
            "new_msisdn": _msisdn("02").value,
        }

    def test_set_primary_noop_when_already_primary(self) -> None:
        user = active_user()
        user.set_primary_phone_number(_msisdn("01"), T0)
        assert user.pull_events() == []

    def test_verify_unknown_number_rejected(self) -> None:
        user = active_user()
        with pytest.raises(PhoneNumberNotFound):
            user.verify_phone_number(_msisdn("09"), T0)


class TestRemovePhoneNumber:
    def test_cannot_remove_last_number(self) -> None:
        user = active_user()
        with pytest.raises(CannotRemoveLastPhoneNumber):
            user.remove_phone_number(_msisdn("01"), T0)

    def test_cannot_remove_primary_number(self) -> None:
        user = active_user()
        user.add_phone_number(_msisdn("02"), T0)
        with pytest.raises(CannotRemovePrimaryPhoneNumber):
            user.remove_phone_number(_msisdn("01"), T0)

    def test_remove_secondary_number(self) -> None:
        user = active_user()
        user.add_phone_number(_msisdn("02"), T0)
        user.pull_events()
        user.remove_phone_number(_msisdn("02"), T0)
        assert user.msisdns == {_msisdn("01")}
        assert [e.name for e in user.pull_events()] == ["PhoneNumberRemoved"]


class TestLifecycleAndKyc:
    def test_freeze_blocks_transactions(self) -> None:
        user = active_user()
        user.freeze("suspicion", T0)
        assert user.status is UserStatus.FROZEN
        with pytest.raises(UserFrozen):
            user.ensure_can_transact()

    def test_freeze_is_idempotent(self) -> None:
        user = active_user()
        user.freeze("x", T0)
        user.pull_events()
        user.freeze("x", T0)
        assert user.pull_events() == []

    def test_unfreeze_restores_active(self) -> None:
        user = active_user()
        user.freeze("x", T0)
        user.unfreeze(T0)
        assert user.is_active
        user.ensure_can_transact()

    def test_unfreeze_noop_when_not_frozen(self) -> None:
        user = active_user()
        user.unfreeze(T0)
        assert user.pull_events() == []

    def test_unfreeze_on_closed_account_rejected(self) -> None:
        user = active_user()
        user.close("x", T0)
        with pytest.raises(AccountClosed):
            user.unfreeze(T0)

    def test_close_is_idempotent(self) -> None:
        user = active_user()
        user.close("x", T0)
        user.pull_events()
        user.close("x", T0)
        assert user.pull_events() == []

    def test_close_then_operations_blocked(self) -> None:
        user = active_user()
        user.close("à la demande du client", T0)
        assert user.status is UserStatus.CLOSED
        with pytest.raises(AccountClosed):
            user.ensure_can_transact()
        with pytest.raises(AccountClosed):
            user.freeze("x", T0)

    def test_pending_user_cannot_transact(self) -> None:
        with pytest.raises(InvalidAccountState):
            make_user().ensure_can_transact()

    def test_verify_and_change_pin(self) -> None:
        from flash.domain.identity.pin import Pin
        from tests.support.fakes import FakePinHasher

        hasher = FakePinHasher()
        user = User.register(
            user_id=EntityId(UUID(int=1)),
            country=CI,
            msisdn=_msisdn("01"),
            pin_hash=hasher.hash(Pin("1397")),
            now=T0,
        )
        assert user.verify_pin(Pin("1397"), hasher) is True
        assert user.verify_pin(Pin("2468"), hasher) is False

        user.pull_events()
        user.change_pin(Pin("2468"), hasher, T0)
        assert user.verify_pin(Pin("2468"), hasher) is True
        assert [e.name for e in user.pull_events()] == ["PinChanged"]

    def test_change_kyc_tier_emits_event_once(self) -> None:
        user = active_user()
        user.change_kyc_tier(KycTier.TIER_1, T0)
        event = user.pull_events()[0]
        assert event.name == "KycTierChanged"
        assert event.to_payload()["new_tier"] == 1
        user.change_kyc_tier(KycTier.TIER_1, T0)  # inchangé
        assert user.pull_events() == []


class TestInvariantsOnReconstruction:
    def test_rejects_zero_phone_numbers(self) -> None:
        with pytest.raises(InvalidAccountState):
            User(
                id=EntityId(UUID(int=1)),
                country=CI,
                status=UserStatus.ACTIVE,
                kyc_tier=KycTier.TIER_0,
                phone_numbers=[],
                created_at=T0,
                pin_hash=PIN_HASH,
            )

    def test_rejects_empty_pin_hash(self) -> None:
        with pytest.raises(InvalidAccountState, match="code secret"):
            User(
                id=EntityId(UUID(int=1)),
                country=CI,
                status=UserStatus.ACTIVE,
                kyc_tier=KycTier.TIER_0,
                phone_numbers=[PhoneNumber(msisdn=_msisdn("01"), linked_at=T0, is_primary=True)],
                created_at=T0,
                pin_hash="",
            )

    def _phone(self, last: str, *, primary: bool = False, verified: bool = True) -> PhoneNumber:
        return PhoneNumber(
            msisdn=_msisdn(last),
            linked_at=T0,
            is_primary=primary,
            verified_at=T0 if verified else None,
        )

    def _build(self, phones: list[PhoneNumber], status: UserStatus = UserStatus.ACTIVE) -> User:
        return User(
            id=EntityId(UUID(int=1)),
            country=CI,
            status=status,
            kyc_tier=KycTier.TIER_0,
            phone_numbers=phones,
            created_at=T0,
            pin_hash=PIN_HASH,
        )

    def test_rejects_more_than_five_numbers(self) -> None:
        phones = [self._phone("01", primary=True)] + [
            self._phone(x) for x in ("02", "03", "04", "05", "06")
        ]
        with pytest.raises(InvalidAccountState, match="Nombre de numéros"):
            self._build(phones)

    def test_rejects_duplicate_numbers(self) -> None:
        phones = [self._phone("01", primary=True), self._phone("01")]
        with pytest.raises(InvalidAccountState, match="double"):
            self._build(phones)

    def test_rejects_zero_or_multiple_primaries_when_not_closed(self) -> None:
        with pytest.raises(InvalidAccountState, match="principal"):
            self._build([self._phone("01"), self._phone("02")])
        with pytest.raises(InvalidAccountState, match="principal"):
            self._build([self._phone("01", primary=True), self._phone("02", primary=True)])

    def test_closed_account_may_have_no_primary(self) -> None:
        user = self._build([self._phone("01")], status=UserStatus.CLOSED)
        assert user.status is UserStatus.CLOSED

    def test_repr_is_informative(self) -> None:
        assert repr(active_user()).startswith("User(id=")

    def test_kyc_tier_labels(self) -> None:
        assert KycTier.TIER_0.label and KycTier.TIER_1.label and KycTier.TIER_2.label
