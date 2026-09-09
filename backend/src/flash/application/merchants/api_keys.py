"""Clés d'API marchand (BE-069) : émission (secret montré une seule fois), liste,
révocation. Le secret n'est jamais persisté — seul son hash l'est.

Port ``MerchantApiKeyVault`` : un adaptateur d'infrastructure fournit la génération d'un
secret aléatoire (``mk_<prefix>_<random>``), son empreinte et la vérification en temps
constant.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable

from flash.application.merchants.operations import NotAMerchant
from flash.application.services import AppServices
from flash.application.transaction import execute_in_uow
from flash.application.unit_of_work import WorkUnitOfWork
from flash.application.use_case import Command, UseCase
from flash.domain.merchants.api_key import MerchantApiKey
from flash.domain.shared.errors import InvalidInput
from flash.domain.shared.identifiers import EntityId


@dataclass(frozen=True, slots=True)
class GeneratedApiKey:
    secret: str
    prefix: str
    secret_hash: str


@runtime_checkable
class MerchantApiKeyVault(Protocol):
    def generate(self) -> GeneratedApiKey: ...

    def hash(self, secret: str) -> str: ...

    def matches(self, secret: str, secret_hash: str) -> bool: ...

    def prefix_of(self, secret: str) -> str: ...


@dataclass(frozen=True, slots=True)
class ApiKeyView:
    key_id: str
    prefix: str
    label: str
    created_at: str
    last_used_at: str | None
    revoked: bool

    @classmethod
    def of(cls, key: MerchantApiKey) -> ApiKeyView:
        return cls(
            key_id=str(key.id),
            prefix=key.prefix,
            label=key.label,
            created_at=key.created_at.isoformat(),
            last_used_at=key.last_used_at.isoformat() if key.last_used_at else None,
            revoked=not key.is_active,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "key_id": self.key_id,
            "prefix": self.prefix,
            "label": self.label,
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
            "revoked": self.revoked,
        }


@dataclass(frozen=True, slots=True)
class IssuedApiKeyView:
    key: ApiKeyView
    secret: str

    def to_dict(self) -> dict[str, Any]:
        return {**self.key.to_dict(), "secret": self.secret}


@dataclass(frozen=True, slots=True)
class IssueMerchantApiKeyCommand(Command):
    merchant_user_id: str
    label: str = ""


class IssueMerchantApiKey(UseCase[IssueMerchantApiKeyCommand, IssuedApiKeyView]):
    def __init__(self, *, services: AppServices, vault: MerchantApiKeyVault) -> None:
        self._services = services
        self._vault = vault

    def execute(self, command: IssueMerchantApiKeyCommand) -> IssuedApiKeyView:
        now = self._services.clock.now()
        generated = self._vault.generate()
        captured: list[IssuedApiKeyView] = []

        def work(uow: WorkUnitOfWork) -> None:
            merchant = uow.merchants.get_by_user_id(EntityId(command.merchant_user_id))
            if merchant is None:
                raise NotAMerchant()
            existing = uow.merchant_api_keys.list_for_merchant(merchant.id)
            if sum(1 for k in existing if k.is_active) >= 10:
                raise InvalidInput("Trop de clés actives (10 maximum). Révoquez-en une.")
            key = MerchantApiKey.issue(
                key_id=self._services.ids.new_id(),
                merchant_id=merchant.id,
                prefix=generated.prefix,
                secret_hash=generated.secret_hash,
                label=command.label,
                now=now,
            )
            uow.merchant_api_keys.add(key)
            captured.append(
                IssuedApiKeyView(key=ApiKeyView.of(key), secret=generated.secret)
            )

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


@dataclass(frozen=True, slots=True)
class ListMerchantApiKeysCommand(Command):
    merchant_user_id: str


class ListMerchantApiKeys(UseCase[ListMerchantApiKeysCommand, list[ApiKeyView]]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: ListMerchantApiKeysCommand) -> list[ApiKeyView]:
        with self._services.uow() as uow:
            merchant = uow.merchants.get_by_user_id(EntityId(command.merchant_user_id))
            if merchant is None:
                raise NotAMerchant()
            return [
                ApiKeyView.of(k) for k in uow.merchant_api_keys.list_for_merchant(merchant.id)
            ]


@dataclass(frozen=True, slots=True)
class RevokeMerchantApiKeyCommand(Command):
    merchant_user_id: str
    key_id: str


class RevokeMerchantApiKey(UseCase[RevokeMerchantApiKeyCommand, ApiKeyView]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: RevokeMerchantApiKeyCommand) -> ApiKeyView:
        now = self._services.clock.now()
        captured: list[ApiKeyView] = []

        def work(uow: WorkUnitOfWork) -> None:
            merchant = uow.merchants.get_by_user_id(EntityId(command.merchant_user_id))
            if merchant is None:
                raise NotAMerchant()
            try:
                key = uow.merchant_api_keys.get(EntityId(command.key_id))
            except ValueError as exc:
                raise InvalidInput("Clé introuvable.") from exc
            if key is None or key.merchant_id != merchant.id:
                raise InvalidInput("Clé introuvable.")
            key.revoke(now)
            uow.merchant_api_keys.save(key)
            captured.append(ApiKeyView.of(key))

        execute_in_uow(self._services.uow, self._services.events, work)
        return captured[0]


__all__ = [
    "ApiKeyView",
    "GeneratedApiKey",
    "IssueMerchantApiKey",
    "IssueMerchantApiKeyCommand",
    "IssuedApiKeyView",
    "ListMerchantApiKeys",
    "ListMerchantApiKeysCommand",
    "MerchantApiKeyVault",
    "RevokeMerchantApiKey",
    "RevokeMerchantApiKeyCommand",
]
