"""Frais négociés par canal (reste de BE-068) — back-office.

Un marchand peut avoir une commission différente selon le canal d'encaissement
(``QR`` en présentiel, ``API`` à distance). En l'absence d'override, ``fee_bps`` par
défaut s'applique. Réservé aux rôles ``admin`` / ``compliance`` ; le changement émet
``MerchantChannelFeeChanged``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flash.application.services import AppServices
from flash.application.transaction import execute_in_uow
from flash.application.unit_of_work import WorkUnitOfWork
from flash.application.use_case import Command, UseCase
from flash.domain.merchants.merchant import Merchant, PaymentChannel
from flash.domain.shared.errors import InvalidInput
from flash.domain.shared.identifiers import EntityId


def _channel(raw: str) -> PaymentChannel:
    try:
        return PaymentChannel(raw.upper())
    except ValueError as exc:
        raise InvalidInput("Canal attendu : QR ou API.") from exc


def _merchant_or_404(uow: WorkUnitOfWork, raw_id: str) -> Merchant:
    try:
        merchant = uow.merchants.get(EntityId(raw_id))
    except ValueError as exc:
        raise InvalidInput("Marchand introuvable.") from exc
    if merchant is None:
        raise InvalidInput("Marchand introuvable.")
    return merchant


@dataclass(frozen=True, slots=True)
class MerchantFeesView:
    merchant_id: str
    default_fee_bps: int
    channel_fees: dict[str, int]

    @classmethod
    def of(cls, merchant: Merchant) -> MerchantFeesView:
        return cls(
            merchant_id=str(merchant.id),
            default_fee_bps=merchant.fee_bps,
            channel_fees=dict(merchant.channel_fees),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "merchant_id": self.merchant_id,
            "default_fee_bps": self.default_fee_bps,
            "channel_fees": self.channel_fees,
        }


@dataclass(frozen=True, slots=True)
class SetMerchantChannelFeeCommand(Command):
    merchant_id: str
    channel: str
    fee_bps: int


class SetMerchantChannelFee(UseCase[SetMerchantChannelFeeCommand, MerchantFeesView]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: SetMerchantChannelFeeCommand) -> MerchantFeesView:
        now = self._services.clock.now()
        channel = _channel(command.channel)
        captured: list[MerchantFeesView] = []

        def work(uow: WorkUnitOfWork) -> None:
            merchant = _merchant_or_404(uow, command.merchant_id)
            merchant.set_channel_fee(channel=channel, fee_bps=command.fee_bps, now=now)
            uow.merchants.save(merchant)
            captured.append(MerchantFeesView.of(merchant))

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


@dataclass(frozen=True, slots=True)
class ClearMerchantChannelFeeCommand(Command):
    merchant_id: str
    channel: str


class ClearMerchantChannelFee(
    UseCase[ClearMerchantChannelFeeCommand, MerchantFeesView]
):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: ClearMerchantChannelFeeCommand) -> MerchantFeesView:
        now = self._services.clock.now()
        channel = _channel(command.channel)
        captured: list[MerchantFeesView] = []

        def work(uow: WorkUnitOfWork) -> None:
            merchant = _merchant_or_404(uow, command.merchant_id)
            merchant.clear_channel_fee(channel=channel, now=now)
            uow.merchants.save(merchant)
            captured.append(MerchantFeesView.of(merchant))

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


@dataclass(frozen=True, slots=True)
class GetMerchantFeesCommand(Command):
    merchant_id: str


class GetMerchantFees(UseCase[GetMerchantFeesCommand, MerchantFeesView]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: GetMerchantFeesCommand) -> MerchantFeesView:
        with self._services.uow() as uow:
            return MerchantFeesView.of(_merchant_or_404(uow, command.merchant_id))


__all__ = [
    "ClearMerchantChannelFee",
    "ClearMerchantChannelFeeCommand",
    "GetMerchantFees",
    "GetMerchantFeesCommand",
    "MerchantFeesView",
    "SetMerchantChannelFee",
    "SetMerchantChannelFeeCommand",
]
