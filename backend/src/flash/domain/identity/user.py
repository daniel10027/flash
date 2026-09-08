"""Agrégat ``User`` — identité et numéros de téléphone (1 à 5).

Invariants garantis par l'agrégat :
- entre 1 et ``MAX_PHONE_NUMBERS`` numéros ;
- exactement un numéro principal tant que le compte n'est pas clôturé ;
- pas de doublon de numéro *au sein du compte* (l'unicité **globale** est du ressort
  du dépôt, qui lève ``PhoneNumberAlreadyLinked`` avant l'ajout) ;
- on ne retire ni le dernier numéro ni le numéro principal ;
- seuls les numéros vérifiés peuvent devenir principaux ;
- un compte gelé ou clôturé ne peut pas initier d'opération monétaire.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import StrEnum

from flash.domain.identity.events import (
    KycTierChanged,
    PhoneNumberAdded,
    PhoneNumberRemoved,
    PhoneNumberVerified,
    PrimaryPhoneNumberChanged,
    UserClosed,
    UserFrozen,
    UserRegistered,
    UserUnfrozen,
)
from flash.domain.identity.kyc import KycTier
from flash.domain.shared.errors import (
    AccountClosed,
    CannotRemoveLastPhoneNumber,
    CannotRemovePrimaryPhoneNumber,
    InvalidAccountState,
    PhoneNumberAlreadyLinked,
    PhoneNumberLimitReached,
    PhoneNumberNotFound,
    PhoneNumberNotVerified,
)
from flash.domain.shared.errors import UserFrozen as UserFrozenError
from flash.domain.shared.events import EventRecorder
from flash.domain.shared.identifiers import CountryCode, EntityId, Msisdn

MAX_PHONE_NUMBERS = 5


class UserStatus(StrEnum):
    PENDING_ACTIVATION = "PENDING_ACTIVATION"
    ACTIVE = "ACTIVE"
    FROZEN = "FROZEN"
    CLOSED = "CLOSED"


@dataclass(frozen=True, slots=True)
class PhoneNumber:
    """Numéro rattaché à un compte. Immuable : les transitions renvoient une copie."""

    msisdn: Msisdn
    linked_at: datetime
    is_primary: bool = False
    verified_at: datetime | None = None

    @property
    def is_verified(self) -> bool:
        return self.verified_at is not None

    def _verified(self, at: datetime) -> PhoneNumber:
        return replace(self, verified_at=at)

    def _with_primary(self, flag: bool) -> PhoneNumber:
        return replace(self, is_primary=flag)


class User(EventRecorder):
    """Racine de l'agrégat identité."""

    def __init__(
        self,
        *,
        id: EntityId,
        country: CountryCode,
        status: UserStatus,
        kyc_tier: KycTier,
        phone_numbers: list[PhoneNumber],
        created_at: datetime,
    ) -> None:
        super().__init__()
        if not phone_numbers:
            raise InvalidAccountState("Un compte doit avoir au moins un numéro.")
        self.id = id
        self.country = country
        self.status = status
        self.kyc_tier = kyc_tier
        self._phones: list[PhoneNumber] = list(phone_numbers)
        self.created_at = created_at
        self._assert_invariants()

    # ------------------------------------------------------------------ fabrique
    @classmethod
    def register(
        cls,
        *,
        user_id: EntityId,
        country: CountryCode,
        msisdn: Msisdn,
        now: datetime,
    ) -> User:
        """Crée un compte en attente d'activation avec un numéro principal non vérifié."""
        user = cls(
            id=user_id,
            country=country,
            status=UserStatus.PENDING_ACTIVATION,
            kyc_tier=KycTier.TIER_0,
            phone_numbers=[PhoneNumber(msisdn=msisdn, linked_at=now, is_primary=True)],
            created_at=now,
        )
        user.record_event(
            UserRegistered(
                occurred_at=now,
                aggregate_id=str(user_id),
                country=country.value,
                primary_msisdn=msisdn.value,
            )
        )
        return user

    # -------------------------------------------------------------- lecture
    @property
    def phone_numbers(self) -> tuple[PhoneNumber, ...]:
        return tuple(self._phones)

    @property
    def primary_phone_number(self) -> PhoneNumber:
        for phone in self._phones:
            if phone.is_primary:
                return phone
        raise InvalidAccountState("Aucun numéro principal défini.")  # pragma: no cover

    @property
    def msisdns(self) -> frozenset[Msisdn]:
        return frozenset(phone.msisdn for phone in self._phones)

    @property
    def is_active(self) -> bool:
        return self.status is UserStatus.ACTIVE

    def _find(self, msisdn: Msisdn) -> PhoneNumber:
        for phone in self._phones:
            if phone.msisdn == msisdn:
                return phone
        raise PhoneNumberNotFound(msisdn=msisdn.masked())

    def _replace_phone(self, old: PhoneNumber, new: PhoneNumber) -> None:
        self._phones = [new if p is old else p for p in self._phones]

    # ---------------------------------------------------------- cycle de vie
    def activate(self, now: datetime) -> None:
        """Active un compte en attente : son numéro principal devient vérifié."""
        if self.status is not UserStatus.PENDING_ACTIVATION:
            raise InvalidAccountState(
                "Seul un compte en attente d'activation peut être activé.",
                status=self.status.value,
            )
        primary = self.primary_phone_number
        self._replace_phone(primary, primary._verified(now))
        self.status = UserStatus.ACTIVE
        self.record_event(
            PhoneNumberVerified(
                occurred_at=now, aggregate_id=str(self.id), msisdn=primary.msisdn.value
            )
        )

    def freeze(self, reason: str, now: datetime) -> None:
        if self.status is UserStatus.CLOSED:
            raise AccountClosed()
        if self.status is UserStatus.FROZEN:
            return
        self.status = UserStatus.FROZEN
        self.record_event(UserFrozen(occurred_at=now, aggregate_id=str(self.id), reason=reason))

    def unfreeze(self, now: datetime) -> None:
        if self.status is UserStatus.CLOSED:
            raise AccountClosed()
        if self.status is not UserStatus.FROZEN:
            return
        self.status = UserStatus.ACTIVE
        self.record_event(UserUnfrozen(occurred_at=now, aggregate_id=str(self.id)))

    def close(self, reason: str, now: datetime) -> None:
        if self.status is UserStatus.CLOSED:
            return
        self.status = UserStatus.CLOSED
        self.record_event(UserClosed(occurred_at=now, aggregate_id=str(self.id), reason=reason))

    def ensure_can_transact(self) -> None:
        """Garde-fou appelé par les cas d'usage avant toute opération monétaire sortante."""
        if self.status is UserStatus.FROZEN:
            raise UserFrozenError()
        if self.status is UserStatus.CLOSED:
            raise AccountClosed()
        if self.status is UserStatus.PENDING_ACTIVATION:
            raise InvalidAccountState("Le compte n'est pas encore activé.")

    # ------------------------------------------------------------- numéros
    def add_phone_number(self, msisdn: Msisdn, now: datetime) -> None:
        if self.status in (UserStatus.FROZEN, UserStatus.CLOSED):
            raise InvalidAccountState(
                "Impossible d'ajouter un numéro sur un compte gelé ou clôturé.",
                status=self.status.value,
            )
        if msisdn in self.msisdns:
            raise PhoneNumberAlreadyLinked("Ce numéro est déjà rattaché à ce compte.")
        if len(self._phones) >= MAX_PHONE_NUMBERS:
            raise PhoneNumberLimitReached(limit=MAX_PHONE_NUMBERS)
        self._phones.append(PhoneNumber(msisdn=msisdn, linked_at=now, is_primary=False))
        self.record_event(
            PhoneNumberAdded(occurred_at=now, aggregate_id=str(self.id), msisdn=msisdn.value)
        )

    def verify_phone_number(self, msisdn: Msisdn, now: datetime) -> None:
        phone = self._find(msisdn)
        if phone.is_verified:
            return
        self._replace_phone(phone, phone._verified(now))
        self.record_event(
            PhoneNumberVerified(occurred_at=now, aggregate_id=str(self.id), msisdn=msisdn.value)
        )

    def remove_phone_number(self, msisdn: Msisdn, now: datetime) -> None:
        phone = self._find(msisdn)
        if len(self._phones) == 1:
            raise CannotRemoveLastPhoneNumber()
        if phone.is_primary:
            raise CannotRemovePrimaryPhoneNumber()
        self._phones = [p for p in self._phones if p is not phone]
        self.record_event(
            PhoneNumberRemoved(occurred_at=now, aggregate_id=str(self.id), msisdn=msisdn.value)
        )

    def set_primary_phone_number(self, msisdn: Msisdn, now: datetime) -> None:
        target = self._find(msisdn)
        if target.is_primary:
            return
        if not target.is_verified:
            raise PhoneNumberNotVerified(msisdn=msisdn.masked())
        previous = self.primary_phone_number
        # ``target`` n'est pas le principal (vérifié plus haut) : les deux objets diffèrent.
        self._replace_phone(previous, previous._with_primary(False))
        self._replace_phone(target, target._with_primary(True))
        self.record_event(
            PrimaryPhoneNumberChanged(
                occurred_at=now,
                aggregate_id=str(self.id),
                previous_msisdn=previous.msisdn.value,
                new_msisdn=msisdn.value,
            )
        )

    # ----------------------------------------------------------------- KYC
    def change_kyc_tier(self, new_tier: KycTier, now: datetime) -> None:
        if new_tier == self.kyc_tier:
            return
        previous = self.kyc_tier
        self.kyc_tier = new_tier
        self.record_event(
            KycTierChanged(
                occurred_at=now,
                aggregate_id=str(self.id),
                previous_tier=int(previous),
                new_tier=int(new_tier),
            )
        )

    # ------------------------------------------------------------ invariants
    def _assert_invariants(self) -> None:
        count = len(self._phones)
        if not 1 <= count <= MAX_PHONE_NUMBERS:
            raise InvalidAccountState(f"Nombre de numéros invalide : {count}.")
        distinct = {p.msisdn for p in self._phones}
        if len(distinct) != count:
            raise InvalidAccountState("Numéros en double sur le compte.")
        primaries = sum(1 for p in self._phones if p.is_primary)
        if self.status is not UserStatus.CLOSED and primaries != 1:
            raise InvalidAccountState(
                f"Il doit y avoir exactement un numéro principal (trouvé {primaries})."
            )

    def __repr__(self) -> str:
        return f"User(id={self.id!s}, status={self.status.value}, phones={len(self._phones)})"


__all__ = ["MAX_PHONE_NUMBERS", "PhoneNumber", "User", "UserStatus"]
