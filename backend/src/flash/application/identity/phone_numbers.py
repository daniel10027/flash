"""Gestion des numéros de téléphone d'un compte (BE-028).

Un compte porte 1 à 5 numéros, un seul principal. Ajouter un numéro envoie un OTP au
nouveau numéro ; il n'est vérifié qu'après confirmation du code. Seul un numéro vérifié
peut devenir principal. L'unicité **globale** (un numéro = un compte) est vérifiée ici
avant l'ajout, en complément de la contrainte de base.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flash.application.ports import OtpPurpose, OtpService
from flash.application.services import AppServices
from flash.application.transaction import execute_in_uow
from flash.application.use_case import Command, UseCase
from flash.domain.identity.user import PhoneNumber, User, UserStatus
from flash.domain.shared.errors import InvalidInput, PhoneNumberAlreadyLinked, UserFrozen
from flash.domain.shared.identifiers import CountryCode, EntityId, Msisdn


@dataclass(frozen=True, slots=True)
class PhoneNumberView:
    phone_number: str
    masked: str
    is_primary: bool
    is_verified: bool
    linked_at: str

    @classmethod
    def of(cls, phone: PhoneNumber) -> PhoneNumberView:
        return cls(
            phone_number=phone.msisdn.value,
            masked=phone.msisdn.masked(),
            is_primary=phone.is_primary,
            is_verified=phone.is_verified,
            linked_at=phone.linked_at.isoformat(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "phone_number": self.phone_number,
            "masked": self.masked,
            "is_primary": self.is_primary,
            "is_verified": self.is_verified,
            "linked_at": self.linked_at,
        }


def _parse_msisdn(raw: str, country: str | None) -> Msisdn:
    try:
        cc = CountryCode(country.upper()) if country else None
        return Msisdn.parse(raw, default_country=cc)
    except ValueError as exc:
        raise InvalidInput(str(exc)) from exc


def _load_user(uow: Any, user_id: str) -> User:
    user: User | None = uow.users.get(EntityId(user_id))
    if user is None:  # pragma: no cover - un jeton valide garantit l'existence
        raise InvalidInput("Compte introuvable.")
    return user


# ------------------------------------------------------------------- lister
@dataclass(frozen=True, slots=True)
class ListPhoneNumbersCommand(Command):
    user_id: str


class ListPhoneNumbers(UseCase[ListPhoneNumbersCommand, list[PhoneNumberView]]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: ListPhoneNumbersCommand) -> list[PhoneNumberView]:
        with self._services.uow() as uow:
            user = _load_user(uow, command.user_id)
            return [PhoneNumberView.of(p) for p in user.phone_numbers]


# ------------------------------------------------------------------- ajouter
@dataclass(frozen=True, slots=True)
class AddPhoneNumberCommand(Command):
    user_id: str
    phone_number: str
    country: str | None = None


@dataclass(frozen=True, slots=True)
class AddPhoneNumberResult:
    masked: str
    verification_required: bool = True


class AddPhoneNumber(UseCase[AddPhoneNumberCommand, AddPhoneNumberResult]):
    def __init__(self, *, services: AppServices, otp: OtpService) -> None:
        self._services = services
        self._otp = otp

    def execute(self, command: AddPhoneNumberCommand) -> AddPhoneNumberResult:
        msisdn = _parse_msisdn(command.phone_number, command.country)
        now = self._services.clock.now()

        def work(uow: Any) -> None:
            user = _load_user(uow, command.user_id)
            if user.status in (UserStatus.FROZEN, UserStatus.CLOSED):
                raise UserFrozen()
            if uow.users.exists_with_msisdn(msisdn):
                raise PhoneNumberAlreadyLinked(msisdn=msisdn.masked())
            user.add_phone_number(msisdn, now)  # ≤ 5, pas de doublon local
            uow.users.save(user)

        execute_in_uow(self._services.uow, self._services.events, work)
        self._otp.issue(msisdn, OtpPurpose.ADD_PHONE_NUMBER)
        return AddPhoneNumberResult(masked=msisdn.masked())


# ------------------------------------------------------------------- vérifier
@dataclass(frozen=True, slots=True)
class VerifyPhoneNumberCommand(Command):
    user_id: str
    phone_number: str
    code: str
    country: str | None = None


class VerifyPhoneNumber(UseCase[VerifyPhoneNumberCommand, PhoneNumberView]):
    def __init__(self, *, services: AppServices, otp: OtpService) -> None:
        self._services = services
        self._otp = otp

    def execute(self, command: VerifyPhoneNumberCommand) -> PhoneNumberView:
        msisdn = _parse_msisdn(command.phone_number, command.country)
        now = self._services.clock.now()
        captured: list[PhoneNumberView] = []

        def work(uow: Any) -> None:
            user = _load_user(uow, command.user_id)
            self._otp.verify(msisdn, OtpPurpose.ADD_PHONE_NUMBER, command.code)
            user.verify_phone_number(msisdn, now)  # PhoneNumberNotFound si absent
            uow.users.save(user)
            phone = next(p for p in user.phone_numbers if p.msisdn == msisdn)
            captured.append(PhoneNumberView.of(phone))

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


# ------------------------------------------------------------------- retirer
@dataclass(frozen=True, slots=True)
class RemovePhoneNumberCommand(Command):
    user_id: str
    phone_number: str
    country: str | None = None


class RemovePhoneNumber(UseCase[RemovePhoneNumberCommand, None]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: RemovePhoneNumberCommand) -> None:
        msisdn = _parse_msisdn(command.phone_number, command.country)
        now = self._services.clock.now()

        def work(uow: Any) -> None:
            user = _load_user(uow, command.user_id)
            user.remove_phone_number(msisdn, now)  # ni le dernier, ni le principal
            uow.users.save(user)

        execute_in_uow(self._services.uow, self._services.events, work)


# ------------------------------------------------------------------- principal
@dataclass(frozen=True, slots=True)
class SetPrimaryPhoneNumberCommand(Command):
    user_id: str
    phone_number: str
    country: str | None = None


class SetPrimaryPhoneNumber(UseCase[SetPrimaryPhoneNumberCommand, list[PhoneNumberView]]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: SetPrimaryPhoneNumberCommand) -> list[PhoneNumberView]:
        msisdn = _parse_msisdn(command.phone_number, command.country)
        now = self._services.clock.now()
        captured: list[list[PhoneNumberView]] = []

        def work(uow: Any) -> None:
            user = _load_user(uow, command.user_id)
            user.set_primary_phone_number(msisdn, now)  # doit être vérifié
            uow.users.save(user)
            captured.append([PhoneNumberView.of(p) for p in user.phone_numbers])

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


__all__ = [
    "AddPhoneNumber",
    "AddPhoneNumberCommand",
    "AddPhoneNumberResult",
    "ListPhoneNumbers",
    "ListPhoneNumbersCommand",
    "PhoneNumberView",
    "RemovePhoneNumber",
    "RemovePhoneNumberCommand",
    "SetPrimaryPhoneNumber",
    "SetPrimaryPhoneNumberCommand",
    "VerifyPhoneNumber",
    "VerifyPhoneNumberCommand",
]
