"""Sous-comptes marchands : caisses & employés (reste de BE-068).

Libre-service marchand : le titulaire du compte marchand crée / liste / met à jour ses
caisses et ses employés. Un sous-compte est une **étiquette d'attribution** portée par
les paiements — pas de portefeuille ni de compte ledger propre.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from flash.application.merchants.operations import NotAMerchant
from flash.application.services import AppServices
from flash.application.transaction import execute_in_uow
from flash.application.unit_of_work import WorkUnitOfWork
from flash.application.use_case import Command, UseCase
from flash.domain.merchants.sub_account import MerchantSubAccount, SubAccountKind
from flash.domain.shared.errors import InvalidInput
from flash.domain.shared.identifiers import EntityId

_MAX_SUB_ACCOUNTS = 200


def _kind(raw: str) -> SubAccountKind:
    try:
        return SubAccountKind(raw.upper())
    except ValueError as exc:
        raise InvalidInput("Type attendu : TILL (caisse) ou EMPLOYEE (employé).") from exc


@dataclass(frozen=True, slots=True)
class SubAccountView:
    id: str
    merchant_id: str
    kind: str
    label: str
    external_ref: str | None
    active: bool
    created_at: str

    @classmethod
    def of(cls, sub: MerchantSubAccount) -> SubAccountView:
        return cls(
            id=str(sub.id),
            merchant_id=str(sub.merchant_id),
            kind=sub.kind.value,
            label=sub.label,
            external_ref=sub.external_ref,
            active=sub.active,
            created_at=sub.created_at.isoformat(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "merchant_id": self.merchant_id,
            "kind": self.kind,
            "label": self.label,
            "external_ref": self.external_ref,
            "active": self.active,
            "created_at": self.created_at,
        }


@dataclass(frozen=True, slots=True)
class CreateSubAccountCommand(Command):
    merchant_user_id: str
    kind: str
    label: str
    external_ref: str | None = None


class CreateSubAccount(UseCase[CreateSubAccountCommand, SubAccountView]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: CreateSubAccountCommand) -> SubAccountView:
        now = self._services.clock.now()
        sub_id = self._services.ids.new_id()
        kind = _kind(command.kind)
        captured: list[SubAccountView] = []

        def work(uow: WorkUnitOfWork) -> None:
            merchant = uow.merchants.get_by_user_id(EntityId(command.merchant_user_id))
            if merchant is None:
                raise NotAMerchant()
            existing = uow.merchant_sub_accounts.list_for_merchant(merchant.id)
            if len(existing) >= _MAX_SUB_ACCOUNTS:
                raise InvalidInput(
                    f"Nombre maximum de caisses / employés atteint ({_MAX_SUB_ACCOUNTS})."
                )
            sub = MerchantSubAccount.open(
                sub_account_id=sub_id,
                merchant_id=merchant.id,
                kind=kind,
                label=command.label,
                now=now,
                external_ref=command.external_ref,
            )
            uow.merchant_sub_accounts.add(sub)
            captured.append(SubAccountView.of(sub))

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


@dataclass(frozen=True, slots=True)
class ListSubAccountsCommand(Command):
    merchant_user_id: str
    include_inactive: bool = True


class ListSubAccounts(UseCase[ListSubAccountsCommand, list[SubAccountView]]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: ListSubAccountsCommand) -> list[SubAccountView]:
        with self._services.uow() as uow:
            merchant = uow.merchants.get_by_user_id(EntityId(command.merchant_user_id))
            if merchant is None:
                raise NotAMerchant()
            rows = uow.merchant_sub_accounts.list_for_merchant(merchant.id)
            return [
                SubAccountView.of(s)
                for s in rows
                if command.include_inactive or s.active
            ]


@dataclass(frozen=True, slots=True)
class UpdateSubAccountCommand(Command):
    merchant_user_id: str
    sub_account_id: str
    label: str | None = None
    external_ref: str | None = None
    active: bool | None = None


class UpdateSubAccount(UseCase[UpdateSubAccountCommand, SubAccountView]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: UpdateSubAccountCommand) -> SubAccountView:
        now = self._services.clock.now()
        captured: list[SubAccountView] = []

        def work(uow: WorkUnitOfWork) -> None:
            merchant = uow.merchants.get_by_user_id(EntityId(command.merchant_user_id))
            if merchant is None:
                raise NotAMerchant()
            try:
                sub = uow.merchant_sub_accounts.get(EntityId(command.sub_account_id))
            except ValueError as exc:
                raise InvalidInput("Identifiant de caisse / employé invalide.") from exc
            if sub is None or sub.merchant_id != merchant.id:
                raise InvalidInput("Caisse / employé introuvable.")
            sub.update(
                now=now,
                label=command.label,
                external_ref=command.external_ref,
                active=command.active,
            )
            uow.merchant_sub_accounts.save(sub)
            captured.append(SubAccountView.of(sub))

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


__all__ = [
    "CreateSubAccount",
    "CreateSubAccountCommand",
    "ListSubAccounts",
    "ListSubAccountsCommand",
    "SubAccountView",
    "UpdateSubAccount",
    "UpdateSubAccountCommand",
]
