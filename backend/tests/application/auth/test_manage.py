"""Tests des compléments BE-027 : appareils connectés, changement et
réinitialisation du code secret (``flash.application.auth.manage``)."""

from __future__ import annotations

from uuid import UUID

import pytest

from flash.application.auth.manage import (
    ChangePin,
    ChangePinCommand,
    ConfirmPinReset,
    ConfirmPinResetCommand,
    ListDevices,
    ListDevicesCommand,
    RequestPinReset,
    RequestPinResetCommand,
    RevokeDevice,
    RevokeDeviceCommand,
)
from flash.application.ports import OtpPurpose
from flash.application.services import AppServices
from flash.domain.identity.pin import Pin
from flash.domain.identity.user import User
from flash.domain.shared.errors import (
    InvalidCredentials,
    InvalidInput,
    OtpInvalid,
)
from flash.domain.shared.identifiers import CountryCode, EntityId, Msisdn
from tests.support.fakes import (
    FakePinHasher,
    FixedClock,
    InMemoryIdempotencyStore,
    RecordingEventPublisher,
    SeqIdGenerator,
)
from tests.support.otp import RecordingOtpService
from tests.support.repositories import InMemoryUnitOfWork
from tests.support.security import InMemoryRefreshTokenStore

CI = CountryCode("CI")
USER_ID = str(UUID(int=1))
MSISDN = "+2250700000001"
PIN = "1397"


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


@pytest.fixture
def services(uow: InMemoryUnitOfWork) -> AppServices:
    return AppServices(
        uow=lambda: uow,
        clock=FixedClock(),
        ids=SeqIdGenerator(),
        events=RecordingEventPublisher(),
        idempotency=InMemoryIdempotencyStore(),
    )


def _user(uow: InMemoryUnitOfWork, *, pin: str = PIN) -> User:
    user = User.register(
        user_id=EntityId(USER_ID),
        country=CI,
        msisdn=Msisdn(MSISDN),
        pin_hash=FakePinHasher().hash(Pin(pin)),
        now=FixedClock().now(),
    )
    user.activate(FixedClock().now())
    user.pull_events()
    uow.users.add(user)
    return user


# --------------------------------------------------------------------- appareils
class TestDevices:
    def test_list_devices_marks_current_and_sorts_recent_first(self) -> None:
        store = InMemoryRefreshTokenStore()
        store.remember(user_id=USER_ID, device_id="d1", jti="j1", ttl_seconds=60, now="2026-01-01")
        store.remember(user_id=USER_ID, device_id="d2", jti="j2", ttl_seconds=60, now="2026-02-01")
        store.remember(user_id="other", device_id="dx", jti="jx", ttl_seconds=60)

        views = ListDevices(refresh_store=store).execute(
            ListDevicesCommand(user_id=USER_ID, current_device_id="d1")
        )

        assert [v.device_id for v in views] == ["d2", "d1"]
        assert [v.current for v in views] == [False, True]
        assert views[1].first_seen == "2026-01-01"

    def test_revoke_device_forgets_only_that_device(self) -> None:
        store = InMemoryRefreshTokenStore()
        store.remember(user_id=USER_ID, device_id="d1", jti="j1", ttl_seconds=60)
        store.remember(user_id=USER_ID, device_id="d2", jti="j2", ttl_seconds=60)

        RevokeDevice(refresh_store=store).execute(
            RevokeDeviceCommand(user_id=USER_ID, device_id="d1")
        )

        assert not store.is_current(user_id=USER_ID, device_id="d1", jti="j1")
        assert store.is_current(user_id=USER_ID, device_id="d2", jti="j2")


# ------------------------------------------------------------------- change-pin
class TestChangePin:
    def _run(self, services: AppServices, **over: str) -> None:
        base = {"user_id": USER_ID, "current_pin": PIN, "new_pin": "2468"}
        base.update(over)
        ChangePin(services=services, pins=FakePinHasher()).execute(ChangePinCommand(**base))

    def test_change_pin_updates_hash(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        self._run(services)
        user = uow.users.get(EntityId(USER_ID))
        assert user is not None
        assert user.verify_pin(Pin("2468"), FakePinHasher())
        assert not user.verify_pin(Pin(PIN), FakePinHasher())

    def test_wrong_current_pin_is_invalid_credentials(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        with pytest.raises(InvalidCredentials):
            self._run(services, current_pin="9753")

    def test_unknown_user_is_invalid_credentials(self, services: AppServices) -> None:
        with pytest.raises(InvalidCredentials):
            self._run(services)

    def test_malformed_pin_is_invalid_input(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        with pytest.raises(InvalidInput):
            self._run(services, new_pin="ab")


# --------------------------------------------------------------------- reset-pin
class TestPinReset:
    def test_request_issues_otp_for_known_number(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        otp = RecordingOtpService()
        RequestPinReset(services=services, otp=otp).execute(
            RequestPinResetCommand(phone_number=MSISDN, country="CI")
        )
        assert otp.issued == [(MSISDN, OtpPurpose.PIN_RESET)]

    def test_request_is_silent_for_unknown_number(self, services: AppServices) -> None:
        otp = RecordingOtpService()
        RequestPinReset(services=services, otp=otp).execute(
            RequestPinResetCommand(phone_number=MSISDN, country="CI")
        )
        assert otp.issued == []

    def test_request_malformed_input_is_invalid_input(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput):
            RequestPinReset(services=services, otp=RecordingOtpService()).execute(
                RequestPinResetCommand(phone_number="nope", country="CI")
            )

    def test_confirm_sets_new_pin_and_revokes_all_sessions(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        store = InMemoryRefreshTokenStore()
        store.remember(user_id=USER_ID, device_id="d1", jti="j1", ttl_seconds=60)
        store.remember(user_id=USER_ID, device_id="d2", jti="j2", ttl_seconds=60)
        otp = RecordingOtpService()
        otp.issue(Msisdn(MSISDN), OtpPurpose.PIN_RESET)

        ConfirmPinReset(
            services=services, otp=otp, pins=FakePinHasher(), refresh_store=store
        ).execute(
            ConfirmPinResetCommand(
                phone_number=MSISDN, country="CI", code="000000", new_pin="2468"
            )
        )

        user = uow.users.get(EntityId(USER_ID))
        assert user is not None and user.verify_pin(Pin("2468"), FakePinHasher())
        assert store.list_devices(user_id=USER_ID) == []

    def test_confirm_with_bad_code_is_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        _user(uow)
        otp = RecordingOtpService()
        otp.issue(Msisdn(MSISDN), OtpPurpose.PIN_RESET)
        with pytest.raises(OtpInvalid):
            ConfirmPinReset(
                services=services,
                otp=otp,
                pins=FakePinHasher(),
                refresh_store=InMemoryRefreshTokenStore(),
            ).execute(
                ConfirmPinResetCommand(
                    phone_number=MSISDN, country="CI", code="999999", new_pin="2468"
                )
            )

    def test_confirm_unknown_user_after_valid_otp_is_invalid_credentials(
        self, services: AppServices
    ) -> None:
        otp = RecordingOtpService()
        otp.issue(Msisdn(MSISDN), OtpPurpose.PIN_RESET)
        with pytest.raises(InvalidCredentials):
            ConfirmPinReset(
                services=services,
                otp=otp,
                pins=FakePinHasher(),
                refresh_store=InMemoryRefreshTokenStore(),
            ).execute(
                ConfirmPinResetCommand(
                    phone_number=MSISDN, country="CI", code="000000", new_pin="2468"
                )
            )

    def test_confirm_malformed_input_is_invalid_input(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput):
            ConfirmPinReset(
                services=services,
                otp=RecordingOtpService(),
                pins=FakePinHasher(),
                refresh_store=InMemoryRefreshTokenStore(),
            ).execute(
                ConfirmPinResetCommand(
                    phone_number=MSISDN, country="CI", code="000000", new_pin="x"
                )
            )
