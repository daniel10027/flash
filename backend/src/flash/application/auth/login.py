"""Cas d'usage ``Login`` (BE-027) — connexion par numéro + code secret.

Vérifie le PIN, refuse un compte non activé, gelé ou clôturé, et renvoie une paire de
jetons liée à l'appareil. Les erreurs de numéro ou de PIN sont **indifférenciées**
(``InvalidCredentials``) pour ne pas révéler l'existence d'un compte.
"""

from __future__ import annotations

from dataclasses import dataclass

from flash.application.auth.results import SessionTokens
from flash.application.auth.tokens import TokenService
from flash.application.services import AppServices
from flash.application.use_case import Command, UseCase
from flash.domain.identity.pin import Pin, PinHasher
from flash.domain.identity.user import User, UserStatus
from flash.domain.shared.errors import (
    AccountClosed,
    InvalidAccountState,
    InvalidCredentials,
    InvalidInput,
    UserFrozen,
)
from flash.domain.shared.identifiers import CountryCode, Msisdn


@dataclass(frozen=True, slots=True)
class LoginCommand(Command):
    phone_number: str
    country: str
    pin: str
    device_id: str


class Login(UseCase[LoginCommand, SessionTokens]):
    def __init__(self, *, services: AppServices, pins: PinHasher, tokens: TokenService) -> None:
        self._services = services
        self._pins = pins
        self._tokens = tokens

    def execute(self, command: LoginCommand) -> SessionTokens:
        try:
            cc = CountryCode(command.country.upper())
            msisdn = Msisdn.parse(command.phone_number, default_country=cc)
            pin = Pin(command.pin)
        except ValueError as exc:
            raise InvalidInput(str(exc)) from exc

        with self._services.uow() as uow:
            user: User | None = uow.users.get_by_msisdn(msisdn)

        if user is None or not user.verify_pin(pin, self._pins):
            raise InvalidCredentials()

        if user.status is UserStatus.PENDING_ACTIVATION:
            raise InvalidAccountState("Activez votre compte avec le code reçu par SMS.")
        if user.status is UserStatus.FROZEN:
            raise UserFrozen()
        if user.status is UserStatus.CLOSED:
            raise AccountClosed()

        pair = self._tokens.issue_pair(user_id=user.id, device_id=command.device_id)
        return SessionTokens.from_pair(pair, user_id=str(user.id))


__all__ = ["Login", "LoginCommand"]
