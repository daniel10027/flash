"""Vérification marchand (KYB, BE-069) : soumission côté marchand + revue back-office."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flash.application.merchants.operations import NotAMerchant
from flash.application.services import AppServices
from flash.application.transaction import execute_in_uow
from flash.application.unit_of_work import WorkUnitOfWork
from flash.application.use_case import Command, UseCase
from flash.domain.merchants.merchant import Merchant
from flash.domain.shared.errors import InvalidInput
from flash.domain.shared.identifiers import EntityId


@dataclass(frozen=True, slots=True)
class MerchantKybView:
    merchant_id: str
    kyb_status: str
    kyb_reviewed_at: str | None
    kyb_reason: str | None

    @classmethod
    def of(cls, merchant: Merchant) -> MerchantKybView:
        return cls(
            merchant_id=str(merchant.id),
            kyb_status=merchant.kyb_status.value,
            kyb_reviewed_at=(
                merchant.kyb_reviewed_at.isoformat() if merchant.kyb_reviewed_at else None
            ),
            kyb_reason=merchant.kyb_reason,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "merchant_id": self.merchant_id,
            "kyb_status": self.kyb_status,
            "kyb_reviewed_at": self.kyb_reviewed_at,
            "kyb_reason": self.kyb_reason,
        }


@dataclass(frozen=True, slots=True)
class SubmitMerchantKybCommand(Command):
    merchant_user_id: str


class SubmitMerchantKyb(UseCase[SubmitMerchantKybCommand, MerchantKybView]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: SubmitMerchantKybCommand) -> MerchantKybView:
        now = self._services.clock.now()
        captured: list[MerchantKybView] = []

        def work(uow: WorkUnitOfWork) -> None:
            merchant = uow.merchants.get_by_user_id(EntityId(command.merchant_user_id))
            if merchant is None:
                raise NotAMerchant()
            merchant.submit_kyb(now)
            uow.merchants.save(merchant)
            captured.append(MerchantKybView.of(merchant))

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


@dataclass(frozen=True, slots=True)
class ReviewMerchantKybCommand(Command):
    merchant_id: str
    reviewer: str
    approve: bool
    reason: str = ""


class ReviewMerchantKyb(UseCase[ReviewMerchantKybCommand, MerchantKybView]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: ReviewMerchantKybCommand) -> MerchantKybView:
        now = self._services.clock.now()
        captured: list[MerchantKybView] = []

        def work(uow: WorkUnitOfWork) -> None:
            try:
                merchant = uow.merchants.get(EntityId(command.merchant_id))
            except ValueError as exc:
                raise InvalidInput("Marchand introuvable.") from exc
            if merchant is None:
                raise InvalidInput("Marchand introuvable.")
            if command.approve:
                merchant.approve_kyb(reviewer=command.reviewer, now=now)
            else:
                merchant.reject_kyb(
                    reviewer=command.reviewer, reason=command.reason, now=now
                )
            uow.merchants.save(merchant)
            captured.append(MerchantKybView.of(merchant))

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


__all__ = [
    "MerchantKybView",
    "ReviewMerchantKyb",
    "ReviewMerchantKybCommand",
    "SubmitMerchantKyb",
    "SubmitMerchantKybCommand",
]
