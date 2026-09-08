"""Tests des cas d'usage de gestion des numéros (BE-028)."""

from __future__ import annotations

from uuid import UUID

import pytest

from flash.application.identity.phone_numbers import (
    AddPhoneNumber,
    AddPhoneNumberCommand,
    ListPhoneNumbers,
    ListPhoneNumbersCommand,
    RemovePhoneNumber,
    RemovePhoneNumberCommand,
    SetPrimaryPhoneNumber,
    SetPrimaryPhoneNumberCommand,
    VerifyPhoneNumber,
    VerifyPhoneNumberCommand,
)
from flash.application.ports import OtpPurpose
from flash.application.services import AppServices
from flash.domain.identity.pin import Pin
from flash.domain.identity.user import User
from flash.domain.shared.errors import (
    CannotRemoveLastPhoneNumber,
    CannotRemovePrimaryPhoneNumber,
    InvalidInput,
    OtpInvalid,
    PhoneNumberAlreadyLinked,
    PhoneNumberLimitReached,
    PhoneNumberNotVerified,
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

CI = CountryCode("CI")
PRIMARY = "+2250700000001"


@pytest.fixture
def uow() -> InMemoryUnitOfWork:
    return InMemoryUnitOfWork()


@pytest.fixture
def otp() -> RecordingOtpService:
    return RecordingOtpService()


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
def user_id(uow: InMemoryUnitOfWork) -> str:
    user = User.register(
        user_id=EntityId(str(UUID(int=1))),
        country=CI,
        msisdn=Msisdn(PRIMARY),
        pin_hash=FakePinHasher().hash(Pin("1397")),
        now=FixedClock().now(),
    )
    user.activate(FixedClock().now())
    user.pull_events()
    uow.users.add(user)
    return str(user.id)


def _add(services: AppServices, otp: RecordingOtpService, user_id: str, number: str) -> None:
    AddPhoneNumber(services=services, otp=otp).execute(
        AddPhoneNumberCommand(user_id=user_id, phone_number=number, country="CI")
    )


def _verify(services: AppServices, otp: RecordingOtpService, user_id: str, number: str) -> None:
    VerifyPhoneNumber(services=services, otp=otp).execute(
        VerifyPhoneNumberCommand(user_id=user_id, phone_number=number, code="000000", country="CI")
    )


class TestAddAndVerify:
    def test_add_creates_unverified_number_and_issues_otp(
        self, services: AppServices, otp: RecordingOtpService, uow: InMemoryUnitOfWork, user_id: str
    ) -> None:
        _add(services, otp, user_id, "+2250700000002")

        user = uow.users.get(EntityId(user_id))
        assert user is not None
        added = next(p for p in user.phone_numbers if p.msisdn == Msisdn("+2250700000002"))
        assert not added.is_verified and not added.is_primary
        assert otp.issued == [("+2250700000002", OtpPurpose.ADD_PHONE_NUMBER)]

    def test_verify_marks_number_verified(
        self, services: AppServices, otp: RecordingOtpService, uow: InMemoryUnitOfWork, user_id: str
    ) -> None:
        _add(services, otp, user_id, "+2250700000002")
        view = VerifyPhoneNumber(services=services, otp=otp).execute(
            VerifyPhoneNumberCommand(
                user_id=user_id, phone_number="+2250700000002", code="000000", country="CI"
            )
        )
        assert view.is_verified is True
        user = uow.users.get(EntityId(user_id))
        assert user is not None
        assert next(
            p for p in user.phone_numbers if p.msisdn == Msisdn("+2250700000002")
        ).is_verified

    def test_verify_wrong_code_rejected(
        self, services: AppServices, otp: RecordingOtpService, user_id: str
    ) -> None:
        _add(services, otp, user_id, "+2250700000002")
        with pytest.raises(OtpInvalid):
            VerifyPhoneNumber(services=services, otp=otp).execute(
                VerifyPhoneNumberCommand(
                    user_id=user_id, phone_number="+2250700000002", code="999999", country="CI"
                )
            )

    def test_cannot_exceed_five_numbers(
        self, services: AppServices, otp: RecordingOtpService, user_id: str
    ) -> None:
        for last in ("02", "03", "04", "05"):
            _add(services, otp, user_id, f"+22507000000{last}")
        with pytest.raises(PhoneNumberLimitReached):
            _add(services, otp, user_id, "+2250700000006")

    def test_number_linked_to_another_account_rejected(
        self, services: AppServices, otp: RecordingOtpService, uow: InMemoryUnitOfWork, user_id: str
    ) -> None:
        other = User.register(
            user_id=EntityId(str(UUID(int=2))),
            country=CI,
            msisdn=Msisdn("+2250700000099"),
            pin_hash="hashed:1397",
            now=FixedClock().now(),
        )
        uow.users.add(other)
        with pytest.raises(PhoneNumberAlreadyLinked):
            _add(services, otp, user_id, "+2250700000099")

    def test_malformed_number_rejected(
        self, services: AppServices, otp: RecordingOtpService, user_id: str
    ) -> None:
        with pytest.raises(InvalidInput):
            _add(services, otp, user_id, "not-a-number")

    def test_frozen_account_cannot_add(
        self, services: AppServices, otp: RecordingOtpService, uow: InMemoryUnitOfWork, user_id: str
    ) -> None:
        user = uow.users.get(EntityId(user_id))
        user.freeze("contrôle", FixedClock().now())  # type: ignore[union-attr]
        uow.users.save(user)  # type: ignore[arg-type]
        with pytest.raises(UserFrozen):
            _add(services, otp, user_id, "+2250700000002")


class TestListRemovePrimary:
    def test_list_returns_all_numbers(
        self, services: AppServices, otp: RecordingOtpService, user_id: str
    ) -> None:
        _add(services, otp, user_id, "+2250700000002")
        views = ListPhoneNumbers(services=services).execute(
            ListPhoneNumbersCommand(user_id=user_id)
        )
        assert {v.phone_number for v in views} == {PRIMARY, "+2250700000002"}
        assert sum(v.is_primary for v in views) == 1

    def test_cannot_remove_primary(
        self, services: AppServices, otp: RecordingOtpService, user_id: str
    ) -> None:
        _add(services, otp, user_id, "+2250700000002")  # un 2e numéro pour ne pas être "le dernier"
        with pytest.raises(CannotRemovePrimaryPhoneNumber):
            RemovePhoneNumber(services=services).execute(
                RemovePhoneNumberCommand(user_id=user_id, phone_number=PRIMARY, country="CI")
            )

    def test_cannot_remove_last(self, services: AppServices, user_id: str) -> None:
        # un seul numéro (le principal) -> retrait interdit
        with pytest.raises(CannotRemoveLastPhoneNumber):
            RemovePhoneNumber(services=services).execute(
                RemovePhoneNumberCommand(user_id=user_id, phone_number=PRIMARY, country="CI")
            )

    def test_remove_secondary(
        self, services: AppServices, otp: RecordingOtpService, uow: InMemoryUnitOfWork, user_id: str
    ) -> None:
        _add(services, otp, user_id, "+2250700000002")
        RemovePhoneNumber(services=services).execute(
            RemovePhoneNumberCommand(user_id=user_id, phone_number="+2250700000002", country="CI")
        )
        user = uow.users.get(EntityId(user_id))
        assert user is not None
        assert {p.msisdn.value for p in user.phone_numbers} == {PRIMARY}

    def test_set_primary_requires_verified(
        self, services: AppServices, otp: RecordingOtpService, user_id: str
    ) -> None:
        _add(services, otp, user_id, "+2250700000002")
        with pytest.raises(PhoneNumberNotVerified):
            SetPrimaryPhoneNumber(services=services).execute(
                SetPrimaryPhoneNumberCommand(
                    user_id=user_id, phone_number="+2250700000002", country="CI"
                )
            )

    def test_set_primary_after_verification(
        self, services: AppServices, otp: RecordingOtpService, uow: InMemoryUnitOfWork, user_id: str
    ) -> None:
        _add(services, otp, user_id, "+2250700000002")
        _verify(services, otp, user_id, "+2250700000002")
        views = SetPrimaryPhoneNumber(services=services).execute(
            SetPrimaryPhoneNumberCommand(
                user_id=user_id, phone_number="+2250700000002", country="CI"
            )
        )
        primary = next(v for v in views if v.is_primary)
        assert primary.phone_number == "+2250700000002"
        assert sum(v.is_primary for v in views) == 1
