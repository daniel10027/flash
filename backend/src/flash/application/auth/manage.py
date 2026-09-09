"""Gestion de la session et du code secret (compléments BE-027).

* ``ListDevices`` / ``RevokeDevice`` — appareils connectés + déconnexion à distance.
* ``ChangePin`` — changer son code secret (authentifié, vérifie l'ancien).
* ``RequestPinReset`` / ``ConfirmPinReset`` — réinitialisation par OTP (numéro non
  authentifié). ``RequestPinReset`` ne révèle jamais si le compte existe. Un reset
  révoque toutes les sessions de l'utilisateur.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flash.application.auth.stores import DeviceRecord, RefreshTokenStore
from flash.application.ports import OtpPurpose, OtpService
from flash.application.services import AppServices
from flash.application.transaction import execute_in_uow
from flash.application.unit_of_work import WorkUnitOfWork
from flash.application.use_case import Command, UseCase
from flash.domain.identity.pin import Pin, PinHasher
from flash.domain.identity.user import User
from flash.domain.shared.errors import InvalidCredentials, InvalidInput
from flash.domain.shared.identifiers import CountryCode, EntityId, Msisdn


@dataclass(frozen=True, slots=True)
class DeviceView:
    device_id: str
    first_seen: str | None
    last_seen: str | None
    current: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "device_id": self.device_id,
            "first_seen": self.first_seen,
            "last_seen": self.last_seen,
            "current": self.current,
        }

    @classmethod
    def of(cls, record: DeviceRecord, *, current_device_id: str) -> DeviceView:
        return cls(
            device_id=record.device_id,
            first_seen=record.first_seen,
            last_seen=record.last_seen,
            current=record.device_id == current_device_id,
        )


@dataclass(frozen=True, slots=True)
class ListDevicesCommand(Command):
    user_id: str
    current_device_id: str


class ListDevices(UseCase[ListDevicesCommand, list[DeviceView]]):
    def __init__(self, *, refresh_store: RefreshTokenStore) -> None:
        self._store = refresh_store

    def execute(self, command: ListDevicesCommand) -> list[DeviceView]:
        return [
            DeviceView.of(r, current_device_id=command.current_device_id)
            for r in self._store.list_devices(user_id=command.user_id)
        ]


@dataclass(frozen=True, slots=True)
class RevokeDeviceCommand(Command):
    user_id: str
    device_id: str


class RevokeDevice(UseCase[RevokeDeviceCommand, None]):
    def __init__(self, *, refresh_store: RefreshTokenStore) -> None:
        self._store = refresh_store

    def execute(self, command: RevokeDeviceCommand) -> None:
        self._store.forget(user_id=command.user_id, device_id=command.device_id)


@dataclass(frozen=True, slots=True)
class ChangePinCommand(Command):
    user_id: str
    current_pin: str
    new_pin: str


class ChangePin(UseCase[ChangePinCommand, None]):
    def __init__(self, *, services: AppServices, pins: PinHasher) -> None:
        self._services = services
        self._pins = pins

    def execute(self, command: ChangePinCommand) -> None:
        try:
            current = Pin(command.current_pin)
            new = Pin(command.new_pin)
        except ValueError as exc:
            raise InvalidInput(str(exc)) from exc
        now = self._services.clock.now()

        def work(uow: WorkUnitOfWork) -> None:
            user = uow.users.get(EntityId(command.user_id))
            if user is None or not user.verify_pin(current, self._pins):
                raise InvalidCredentials()
            user.change_pin(new, self._pins, now)
            uow.users.save(user)

        execute_in_uow(self._services.uow, self._services.events, work)


@dataclass(frozen=True, slots=True)
class RequestPinResetCommand(Command):
    phone_number: str
    country: str


class RequestPinReset(UseCase[RequestPinResetCommand, None]):
    def __init__(self, *, services: AppServices, otp: OtpService) -> None:
        self._services = services
        self._otp = otp

    def execute(self, command: RequestPinResetCommand) -> None:
        try:
            cc = CountryCode(command.country.upper())
            msisdn = Msisdn.parse(command.phone_number, default_country=cc)
        except ValueError as exc:
            raise InvalidInput(str(exc)) from exc
        with self._services.uow() as uow:
            exists = uow.users.get_by_msisdn(msisdn) is not None
        if exists:  # silencieux si le compte n'existe pas — pas de fuite d'information
            self._otp.issue(msisdn, OtpPurpose.PIN_RESET)


@dataclass(frozen=True, slots=True)
class ConfirmPinResetCommand(Command):
    phone_number: str
    country: str
    code: str
    new_pin: str


class ConfirmPinReset(UseCase[ConfirmPinResetCommand, None]):
    def __init__(
        self,
        *,
        services: AppServices,
        otp: OtpService,
        pins: PinHasher,
        refresh_store: RefreshTokenStore,
    ) -> None:
        self._services = services
        self._otp = otp
        self._pins = pins
        self._store = refresh_store

    def execute(self, command: ConfirmPinResetCommand) -> None:
        try:
            cc = CountryCode(command.country.upper())
            msisdn = Msisdn.parse(command.phone_number, default_country=cc)
            new = Pin(command.new_pin)
        except ValueError as exc:
            raise InvalidInput(str(exc)) from exc

        self._otp.verify(msisdn, OtpPurpose.PIN_RESET, command.code)
        now = self._services.clock.now()
        target: list[str] = []

        def work(uow: WorkUnitOfWork) -> None:
            user: User | None = uow.users.get_by_msisdn(msisdn)
            if user is None:
                raise InvalidCredentials()
            user.change_pin(new, self._pins, now)
            uow.users.save(user)
            target.append(str(user.id))

        # ``work`` renseigne toujours ``target`` ou lève (propagé ici) : un reset
        # confirmé révoque toutes les sessions de l'utilisateur.
        execute_in_uow(self._services.uow, self._services.events, work)
        self._store.forget_all(user_id=target[0])


__all__ = [
    "ChangePin",
    "ChangePinCommand",
    "ConfirmPinReset",
    "ConfirmPinResetCommand",
    "DeviceView",
    "ListDevices",
    "ListDevicesCommand",
    "RequestPinReset",
    "RequestPinResetCommand",
    "RevokeDevice",
    "RevokeDeviceCommand",
]
