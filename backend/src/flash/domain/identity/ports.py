"""Ports du sous-domaine identité."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from flash.domain.identity.kyc_case import KycCase
from flash.domain.identity.user import User
from flash.domain.shared.identifiers import EntityId, Msisdn


@runtime_checkable
class UserRepository(Protocol):
    """Persistance de l'agrégat ``User``.

    L'unicité **globale** d'un numéro est de la responsabilité de l'implémentation :
    ``add``/``save`` doivent lever ``PhoneNumberAlreadyLinked`` si un numéro de
    l'agrégat est déjà rattaché à un autre utilisateur (contrainte d'unicité en base).
    """

    def get(self, user_id: EntityId) -> User | None: ...

    def get_by_msisdn(self, msisdn: Msisdn) -> User | None: ...

    def exists_with_msisdn(self, msisdn: Msisdn) -> bool: ...

    def add(self, user: User) -> None: ...

    def save(self, user: User) -> None: ...


@runtime_checkable
class KycCaseRepository(Protocol):
    """Persistance de l'agrégat ``KycCase``."""

    def get(self, case_id: EntityId) -> KycCase | None: ...

    def get_pending_for_user(self, user_id: EntityId) -> KycCase | None: ...

    def list_for_user(self, user_id: EntityId) -> list[KycCase]: ...

    def add(self, case: KycCase) -> None: ...

    def save(self, case: KycCase) -> None: ...


__all__ = ["KycCaseRepository", "UserRepository"]
