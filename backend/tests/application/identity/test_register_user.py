"""Tests du cas d'usage RegisterUser (BE-025)."""

from __future__ import annotations

import pytest

from flash.application.identity.register_user import RegisterUser, RegisterUserCommand
from flash.application.ports import OtpPurpose
from flash.application.services import AppServices
from flash.domain.country.directory import StaticCountryDirectory, UnsupportedCountry
from flash.domain.identity.pin import Pin
from flash.domain.identity.user import UserStatus
from flash.domain.shared.errors import (
    DuplicateOperation,
    InvalidInput,
    PhoneNumberAlreadyLinked,
)
from flash.domain.shared.identifiers import EntityId, IdempotencyKey
from flash.domain.shared.money import XOF, Money
from tests.support.fakes import (
    FakePinHasher,
    FixedClock,
    InMemoryIdempotencyStore,
    RecordingEventPublisher,
    SeqIdGenerator,
)
from tests.support.otp import RecordingOtpService
from tests.support.repositories import InMemoryUnitOfWork

ROUTE = "POST /v1/auth/register"


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


@pytest.fixture
def otp() -> RecordingOtpService:
    return RecordingOtpService()


@pytest.fixture
def events() -> RecordingEventPublisher:
    return RecordingEventPublisher()


@pytest.fixture
def store() -> InMemoryIdempotencyStore:
    return InMemoryIdempotencyStore()


@pytest.fixture
def use_case(
    uow: InMemoryUnitOfWork,
    otp: RecordingOtpService,
    events: RecordingEventPublisher,
    store: InMemoryIdempotencyStore,
) -> RegisterUser:
    services = AppServices(
        uow=lambda: uow,
        clock=FixedClock(),
        ids=SeqIdGenerator(),
        events=events,
        idempotency=store,
    )
    return RegisterUser(
        services=services, countries=StaticCountryDirectory(), pins=FakePinHasher(), otp=otp
    )


def _cmd(**over: str) -> RegisterUserCommand:
    base: dict[str, str] = {
        "phone_number": "0700000001",
        "pin": "1397",
        "country": "ci",
        "idempotency_key": "reg-key-0001",
    }
    base.update(over)
    return RegisterUserCommand(**base)


class TestRegisterUser:
    def test_creates_pending_user_wallet_and_ledger_account(
        self, use_case: RegisterUser, uow: InMemoryUnitOfWork
    ) -> None:
        result = use_case.execute(_cmd())

        assert result.currency == "XOF"
        assert result.activation_required is True
        assert "***" in result.phone_number_masked

        user = uow.users.get(EntityId(result.user_id))
        assert user is not None
        assert user.status is UserStatus.PENDING_ACTIVATION
        assert user.country.value == "CI"
        assert user.verify_pin(Pin("1397"), FakePinHasher()) is True

        wallet = uow.wallets.get(EntityId(result.wallet_id))
        assert wallet is not None
        assert wallet.currency == XOF
        assert wallet.balance == Money(0, XOF)

    def test_sends_activation_otp_once(
        self, use_case: RegisterUser, otp: RecordingOtpService
    ) -> None:
        use_case.execute(_cmd())
        assert [p for _, p in otp.issued] == [OtpPurpose.ACTIVATION]

    def test_publishes_user_and_wallet_events(
        self, use_case: RegisterUser, events: RecordingEventPublisher
    ) -> None:
        use_case.execute(_cmd())
        assert events.names() == ["UserRegistered", "WalletOpened"]

    def test_national_number_is_normalised_to_e164(self, use_case: RegisterUser) -> None:
        result = use_case.execute(_cmd(phone_number="07 00 00 00 02"))
        assert result.phone_number_masked.startswith("+225")

    def test_is_idempotent_on_replay(
        self, use_case: RegisterUser, otp: RecordingOtpService
    ) -> None:
        first = use_case.execute(_cmd())
        second = use_case.execute(_cmd())
        assert (first.user_id, first.wallet_id) == (second.user_id, second.wallet_id)
        assert len(otp.issued) == 1  # l'OTP n'est pas renvoyé

    def test_duplicate_msisdn_rejected(self, use_case: RegisterUser) -> None:
        use_case.execute(_cmd(idempotency_key="dup-key-1"))
        with pytest.raises(PhoneNumberAlreadyLinked):
            use_case.execute(_cmd(idempotency_key="dup-key-2"))

    def test_unsupported_country_rejected(self, use_case: RegisterUser) -> None:
        with pytest.raises(UnsupportedCountry):
            use_case.execute(_cmd(country="US", phone_number="+15551234567"))

    def test_malformed_country_code_rejected(self, use_case: RegisterUser) -> None:
        with pytest.raises(InvalidInput):
            use_case.execute(_cmd(country="XX1"))

    def test_short_idempotency_key_rejected(self, use_case: RegisterUser) -> None:
        with pytest.raises(InvalidInput):
            use_case.execute(_cmd(idempotency_key="short"))

    def test_invalid_pin_rejected(self, use_case: RegisterUser) -> None:
        with pytest.raises(InvalidInput):
            use_case.execute(_cmd(pin="1234"))

    def test_concurrent_inflight_key_raises_duplicate(
        self, use_case: RegisterUser, store: InMemoryIdempotencyStore
    ) -> None:
        scoped = IdempotencyKey("reg-key-0001").scoped(user_id="msisdn:+2250700000001", route=ROUTE)
        store.remember(scoped, ttl_seconds=60)
        with pytest.raises(DuplicateOperation):
            use_case.execute(_cmd())
