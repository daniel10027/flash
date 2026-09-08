"""Cas d'usage ``RegisterUser`` (BE-025).

Crée un compte en attente d'activation à partir d'un numéro, d'un PIN et d'un pays :
- un ``User`` (palier KYC 0) avec le numéro comme principal (non vérifié) ;
- un ``Wallet`` dans la devise du pays ;
- le compte comptable ``CLIENT_LIABILITY`` de l'utilisateur ;
- un code OTP d'activation envoyé par SMS.

Idempotent : rejouer la même clé pour le même numéro renvoie le résultat mémorisé.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flash.application.idempotency import IdempotencyGuard
from flash.application.ports import OtpPurpose, OtpService
from flash.application.services import AppServices
from flash.application.transaction import execute_in_uow
from flash.application.unit_of_work import WorkUnitOfWork
from flash.application.use_case import Command, UseCase
from flash.domain.country.directory import CountryDirectory
from flash.domain.identity.pin import Pin, PinHasher
from flash.domain.identity.user import User
from flash.domain.ledger.chart import AccountType
from flash.domain.shared.errors import InvalidInput, PhoneNumberAlreadyLinked
from flash.domain.shared.identifiers import CountryCode, IdempotencyKey, Msisdn
from flash.domain.shared.money import Currency
from flash.domain.wallet.wallet import Wallet

_ROUTE = "POST /v1/auth/register"


@dataclass(frozen=True, slots=True)
class RegisterUserCommand(Command):
    phone_number: str
    pin: str
    country: str
    idempotency_key: str


@dataclass(frozen=True, slots=True)
class RegisterUserResult:
    user_id: str
    wallet_id: str
    currency: str
    phone_number_masked: str
    activation_required: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "user_id": self.user_id,
            "wallet_id": self.wallet_id,
            "currency": self.currency,
            "phone_number_masked": self.phone_number_masked,
            "activation_required": self.activation_required,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RegisterUserResult:
        return cls(
            user_id=data["user_id"],
            wallet_id=data["wallet_id"],
            currency=data["currency"],
            phone_number_masked=data["phone_number_masked"],
            activation_required=data["activation_required"],
        )


class RegisterUser(UseCase[RegisterUserCommand, RegisterUserResult]):
    def __init__(
        self,
        *,
        services: AppServices,
        countries: CountryDirectory,
        pins: PinHasher,
        otp: OtpService,
    ) -> None:
        self._services = services
        self._countries = countries
        self._pins = pins
        self._otp = otp
        self._guard = IdempotencyGuard(services.idempotency)

    def execute(self, command: RegisterUserCommand) -> RegisterUserResult:
        try:
            country = CountryCode(command.country.upper())
        except ValueError as exc:
            raise InvalidInput(str(exc)) from exc

        currency = self._countries.currency_for(country)  # lève UnsupportedCountry

        try:
            msisdn = Msisdn.parse(command.phone_number, default_country=country)
            pin = Pin(command.pin)
            key = IdempotencyKey(command.idempotency_key)
        except ValueError as exc:
            raise InvalidInput(str(exc)) from exc

        outcome = self._guard.run(
            key=key,
            subject=f"msisdn:{msisdn.value}",
            route=_ROUTE,
            produce=lambda: self._register(country, currency, msisdn, pin),
            rebuild=RegisterUserResult.from_dict,
        )
        return outcome.result

    def _register(
        self, country: CountryCode, currency: Currency, msisdn: Msisdn, pin: Pin
    ) -> tuple[RegisterUserResult, dict[str, Any]]:
        now = self._services.clock.now()
        user_id = self._services.ids.new_id()
        wallet_id = self._services.ids.new_id()

        def work(uow: WorkUnitOfWork) -> None:
            if uow.users.exists_with_msisdn(msisdn):
                raise PhoneNumberAlreadyLinked(msisdn=msisdn.masked())
            user = User.register(
                user_id=user_id,
                country=country,
                msisdn=msisdn,
                pin_hash=self._pins.hash(pin),
                now=now,
            )
            wallet = Wallet.open(wallet_id=wallet_id, user_id=user_id, currency=currency, now=now)
            uow.ledger.ensure_account(
                account_type=AccountType.CLIENT_LIABILITY,
                currency=currency,
                owner_ref=str(user_id),
            )
            uow.users.add(user)
            uow.wallets.add(wallet)

        execute_in_uow(self._services.uow, self._services.events, work)
        self._otp.issue(msisdn, OtpPurpose.ACTIVATION)

        result = RegisterUserResult(
            user_id=str(user_id),
            wallet_id=str(wallet_id),
            currency=currency.code,
            phone_number_masked=msisdn.masked(),
        )
        return result, result.to_dict()


__all__ = ["RegisterUser", "RegisterUserCommand", "RegisterUserResult"]
