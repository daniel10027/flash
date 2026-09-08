"""Tests des cas d'usage d'authentification : Login, VerifyOtp, ResendOtp (BE-026/027)."""

from __future__ import annotations

import pytest

from flash.application.auth.login import Login, LoginCommand
from flash.application.auth.results import SessionTokens
from flash.application.auth.tokens import TokenPair
from flash.application.auth.verify_otp import (
    ResendOtp,
    ResendOtpCommand,
    VerifyOtp,
    VerifyOtpCommand,
)
from flash.application.ports import OtpPurpose
from flash.application.services import AppServices
from flash.domain.country.directory import StaticCountryDirectory
from flash.domain.identity.pin import Pin
from flash.domain.identity.user import User
from flash.domain.shared.errors import (
    AccountClosed,
    InvalidAccountState,
    InvalidCredentials,
    InvalidInput,
    UserFrozen,
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
from tests.support.security import build_test_security

CI = CountryCode("CI")
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


@pytest.fixture
def tokens_service() -> object:
    return build_test_security().tokens


def _make_user(*, activated: bool, msisdn: str = MSISDN) -> User:
    user = User.register(
        user_id=EntityId(f"00000000-0000-0000-0000-{abs(hash(msisdn)) % 10**12:012d}"),
        country=CI,
        msisdn=Msisdn(msisdn),
        pin_hash=FakePinHasher().hash(Pin(PIN)),
        now=FixedClock().now(),
    )
    user.pull_events()
    if activated:
        user.activate(FixedClock().now())
        user.pull_events()
    return user


class TestLogin:
    def _use_case(self, services: AppServices, tokens_service: object) -> Login:
        return Login(services=services, pins=FakePinHasher(), tokens=tokens_service)  # type: ignore[arg-type]

    def _cmd(self, **over: str) -> LoginCommand:
        base = {"phone_number": MSISDN, "country": "CI", "pin": PIN, "device_id": "d1"}
        base.update(over)
        return LoginCommand(**base)

    def test_login_active_user_issues_tokens(
        self, services: AppServices, uow: InMemoryUnitOfWork, tokens_service: object
    ) -> None:
        uow.users.add(_make_user(activated=True))
        result = self._use_case(services, tokens_service).execute(self._cmd())
        assert isinstance(result, SessionTokens)
        assert result.access_token and result.user_id

    def test_unknown_number_is_invalid_credentials(
        self, services: AppServices, tokens_service: object
    ) -> None:
        with pytest.raises(InvalidCredentials):
            self._use_case(services, tokens_service).execute(self._cmd())

    def test_wrong_pin_is_invalid_credentials(
        self, services: AppServices, uow: InMemoryUnitOfWork, tokens_service: object
    ) -> None:
        uow.users.add(_make_user(activated=True))
        with pytest.raises(InvalidCredentials):
            self._use_case(services, tokens_service).execute(self._cmd(pin="9753"))

    def test_pending_account_cannot_login(
        self, services: AppServices, uow: InMemoryUnitOfWork, tokens_service: object
    ) -> None:
        uow.users.add(_make_user(activated=False))
        with pytest.raises(InvalidAccountState):
            self._use_case(services, tokens_service).execute(self._cmd())

    def test_frozen_account_cannot_login(
        self, services: AppServices, uow: InMemoryUnitOfWork, tokens_service: object
    ) -> None:
        user = _make_user(activated=True)
        user.freeze("contrôle", FixedClock().now())
        uow.users.add(user)
        with pytest.raises(UserFrozen):
            self._use_case(services, tokens_service).execute(self._cmd())

    def test_closed_account_cannot_login(
        self, services: AppServices, uow: InMemoryUnitOfWork, tokens_service: object
    ) -> None:
        user = _make_user(activated=True)
        user.close("à la demande", FixedClock().now())
        uow.users.add(user)
        with pytest.raises(AccountClosed):
            self._use_case(services, tokens_service).execute(self._cmd())

    def test_malformed_input_is_invalid_input(
        self, services: AppServices, tokens_service: object
    ) -> None:
        with pytest.raises(InvalidInput):
            self._use_case(services, tokens_service).execute(self._cmd(country="ZZ9"))


class TestVerifyOtp:
    def _use_case(
        self, services: AppServices, otp: RecordingOtpService, tokens_service: object
    ) -> VerifyOtp:
        return VerifyOtp(
            services=services,
            countries=StaticCountryDirectory(),
            otp=otp,
            tokens=tokens_service,  # type: ignore[arg-type]
        )

    def _cmd(self, **over: str) -> VerifyOtpCommand:
        base = {"phone_number": MSISDN, "country": "CI", "code": "000000", "device_id": "d1"}
        base.update(over)
        return VerifyOtpCommand(**base)

    def test_unknown_number_is_invalid_credentials(
        self, services: AppServices, tokens_service: object
    ) -> None:
        otp = RecordingOtpService()
        with pytest.raises(InvalidCredentials):
            self._use_case(services, otp, tokens_service).execute(self._cmd())

    def test_already_active_is_rejected(
        self, services: AppServices, uow: InMemoryUnitOfWork, tokens_service: object
    ) -> None:
        otp = RecordingOtpService()
        uow.users.add(_make_user(activated=True))
        with pytest.raises(InvalidAccountState):
            self._use_case(services, otp, tokens_service).execute(self._cmd())

    def test_activation_flow(
        self, services: AppServices, uow: InMemoryUnitOfWork, tokens_service: object
    ) -> None:
        otp = RecordingOtpService()
        otp.issue(Msisdn(MSISDN), OtpPurpose.ACTIVATION)
        uow.users.add(_make_user(activated=False))
        result = self._use_case(services, otp, tokens_service).execute(self._cmd())
        assert result.access_token
        assert uow.users.get_by_msisdn(Msisdn(MSISDN)).is_active  # type: ignore[union-attr]

    def test_malformed_input_is_invalid_input(
        self, services: AppServices, tokens_service: object
    ) -> None:
        with pytest.raises(InvalidInput):
            self._use_case(services, RecordingOtpService(), tokens_service).execute(
                self._cmd(phone_number="not-a-number")
            )


class TestResendOtp:
    def _use_case(self, services: AppServices, otp: RecordingOtpService) -> ResendOtp:
        return ResendOtp(services=services, countries=StaticCountryDirectory(), otp=otp)

    def test_pending_account_gets_new_code(
        self, services: AppServices, uow: InMemoryUnitOfWork
    ) -> None:
        otp = RecordingOtpService()
        uow.users.add(_make_user(activated=False))
        result = self._use_case(services, otp).execute(
            ResendOtpCommand(phone_number=MSISDN, country="CI")
        )
        assert result.resent is True
        assert otp.issued == [(MSISDN, OtpPurpose.ACTIVATION)]

    def test_unknown_number_is_silent(self, services: AppServices) -> None:
        otp = RecordingOtpService()
        result = self._use_case(services, otp).execute(
            ResendOtpCommand(phone_number=MSISDN, country="CI")
        )
        assert result.resent is True  # réponse indifférenciée
        assert otp.issued == []  # mais aucun code n'est réellement envoyé

    def test_active_account_is_silent(self, services: AppServices, uow: InMemoryUnitOfWork) -> None:
        otp = RecordingOtpService()
        uow.users.add(_make_user(activated=True))
        self._use_case(services, otp).execute(ResendOtpCommand(phone_number=MSISDN, country="CI"))
        assert otp.issued == []

    def test_malformed_input_is_invalid_input(self, services: AppServices) -> None:
        with pytest.raises(InvalidInput):
            self._use_case(services, RecordingOtpService()).execute(
                ResendOtpCommand(phone_number="x", country="CI")
            )


class TestSessionTokens:
    def test_from_pair_with_and_without_user_id(self) -> None:
        pair = TokenPair(
            access_token="a", refresh_token="r", access_expires_in=900, refresh_expires_in=3600
        )
        with_user = SessionTokens.from_pair(pair, user_id="u-1")
        without = SessionTokens.from_pair(pair)
        assert with_user.to_dict()["user_id"] == "u-1"
        assert "user_id" not in without.to_dict()
