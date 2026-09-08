"""Cas d'usage ``VerifyOtp`` et ``ResendOtp`` (BE-026).

``VerifyOtp`` active un compte en attente : vérifie le code d'activation, passe l'état à
``ACTIVE`` (numéro principal vérifié) et renvoie une paire de jetons de session.
``ResendOtp`` renvoie un code d'activation à un compte encore en attente.
"""

from __future__ import annotations

from dataclasses import dataclass

from flash.application.auth.results import SessionTokens
from flash.application.auth.tokens import TokenService
from flash.application.ports import OtpPurpose, OtpService
from flash.application.services import AppServices
from flash.application.transaction import execute_in_uow
from flash.application.use_case import Command, UseCase
from flash.domain.country.directory import CountryDirectory
from flash.domain.identity.user import User, UserStatus
from flash.domain.shared.errors import InvalidAccountState, InvalidCredentials, InvalidInput
from flash.domain.shared.identifiers import CountryCode, EntityId, Msisdn


@dataclass(frozen=True, slots=True)
class VerifyOtpCommand(Command):
    phone_number: str
    country: str
    code: str
    device_id: str


@dataclass(frozen=True, slots=True)
class ResendOtpCommand(Command):
    phone_number: str
    country: str


@dataclass(frozen=True, slots=True)
class ResendOtpResult:
    phone_number_masked: str
    resent: bool = True


def _parse(phone_number: str, country: str) -> tuple[CountryCode, Msisdn]:
    try:
        cc = CountryCode(country.upper())
        return cc, Msisdn.parse(phone_number, default_country=cc)
    except ValueError as exc:
        raise InvalidInput(str(exc)) from exc


class VerifyOtp(UseCase[VerifyOtpCommand, SessionTokens]):
    def __init__(
        self,
        *,
        services: AppServices,
        countries: CountryDirectory,
        otp: OtpService,
        tokens: TokenService,
    ) -> None:
        self._services = services
        self._countries = countries
        self._otp = otp
        self._tokens = tokens

    def execute(self, command: VerifyOtpCommand) -> SessionTokens:
        _, msisdn = _parse(command.phone_number, command.country)
        now = self._services.clock.now()
        activated: list[EntityId] = []

        def work(uow: object) -> None:
            user: User | None = uow.users.get_by_msisdn(msisdn)  # type: ignore[attr-defined]
            if user is None:
                raise InvalidCredentials("Aucun compte pour ce numéro.")
            if user.status is not UserStatus.PENDING_ACTIVATION:
                raise InvalidAccountState("Ce compte est déjà activé.", status=user.status.value)
            self._otp.verify(msisdn, OtpPurpose.ACTIVATION, command.code)
            user.activate(now)
            uow.users.save(user)  # type: ignore[attr-defined]
            activated.append(user.id)

        execute_in_uow(self._services.uow, self._services.events, work)
        pair = self._tokens.issue_pair(user_id=activated[0], device_id=command.device_id)
        return SessionTokens.from_pair(pair, user_id=str(activated[0]))


class ResendOtp(UseCase[ResendOtpCommand, ResendOtpResult]):
    def __init__(
        self, *, services: AppServices, countries: CountryDirectory, otp: OtpService
    ) -> None:
        self._services = services
        self._countries = countries
        self._otp = otp

    def execute(self, command: ResendOtpCommand) -> ResendOtpResult:
        _, msisdn = _parse(command.phone_number, command.country)

        with self._services.uow() as uow:
            user: User | None = uow.users.get_by_msisdn(msisdn)  # type: ignore[attr-defined]
            status = user.status if user is not None else None

        if user is None or status is not UserStatus.PENDING_ACTIVATION:
            # Réponse indifférenciée : on n'indique pas si le numéro existe / est activé.
            return ResendOtpResult(phone_number_masked=msisdn.masked())

        self._otp.issue(msisdn, OtpPurpose.ACTIVATION)
        return ResendOtpResult(phone_number_masked=msisdn.masked())


__all__ = [
    "ResendOtp",
    "ResendOtpCommand",
    "ResendOtpResult",
    "VerifyOtp",
    "VerifyOtpCommand",
]
