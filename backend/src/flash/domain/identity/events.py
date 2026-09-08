"""Événements de l'agrégat identité."""

from __future__ import annotations

from dataclasses import dataclass

from flash.domain.shared.events import DomainEvent


@dataclass(frozen=True, slots=True, kw_only=True)
class UserRegistered(DomainEvent):
    country: str
    primary_msisdn: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PhoneNumberAdded(DomainEvent):
    msisdn: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PhoneNumberVerified(DomainEvent):
    msisdn: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PhoneNumberRemoved(DomainEvent):
    msisdn: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PrimaryPhoneNumberChanged(DomainEvent):
    previous_msisdn: str
    new_msisdn: str


@dataclass(frozen=True, slots=True, kw_only=True)
class KycTierChanged(DomainEvent):
    previous_tier: int
    new_tier: int


@dataclass(frozen=True, slots=True, kw_only=True)
class KycCaseSubmitted(DomainEvent):
    user_id: str
    target_tier: int
    document_kinds: list[str]


@dataclass(frozen=True, slots=True, kw_only=True)
class KycCaseApproved(DomainEvent):
    user_id: str
    target_tier: int
    reviewer_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class KycCaseRejected(DomainEvent):
    user_id: str
    reviewer_id: str
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class KycCaseWithdrawn(DomainEvent):
    user_id: str


@dataclass(frozen=True, slots=True, kw_only=True)
class PinChanged(DomainEvent):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class UserFrozen(DomainEvent):
    reason: str


@dataclass(frozen=True, slots=True, kw_only=True)
class UserUnfrozen(DomainEvent):
    pass


@dataclass(frozen=True, slots=True, kw_only=True)
class UserClosed(DomainEvent):
    reason: str


__all__ = [
    "KycCaseApproved",
    "KycCaseRejected",
    "KycCaseSubmitted",
    "KycCaseWithdrawn",
    "KycTierChanged",
    "PhoneNumberAdded",
    "PhoneNumberRemoved",
    "PhoneNumberVerified",
    "PinChanged",
    "PrimaryPhoneNumberChanged",
    "UserClosed",
    "UserFrozen",
    "UserRegistered",
    "UserUnfrozen",
]
