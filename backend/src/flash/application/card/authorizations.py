"""Flux d'autorisation carte (BE-057) — appelé par le réseau via un webhook signé.

``authorize`` réserve les fonds sur le portefeuille (aucune écriture ledger). ``capture``
consomme la réserve et écrit une ``CARD_CAPTURE`` (``CARD_SCHEME_SUSPENSE``). ``reverse``
rend la réserve d'une autorisation non capturée. ``refund`` restitue au client des fonds
déjà capturés (``CARD_REFUND``). Tout est idempotent par ``authorization_id`` : la ligne
``CardAuthorization`` **est** l'enregistrement d'idempotence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

from flash.application.services import AppServices
from flash.application.transaction import execute_in_uow
from flash.application.unit_of_work import WorkUnitOfWork
from flash.application.use_case import Command, UseCase
from flash.domain.card.authorization import CardAuthorization
from flash.domain.card.card import CardChannel
from flash.domain.ledger.chart import AccountType
from flash.domain.ledger.transaction import LedgerTransaction
from flash.domain.shared.errors import DomainError, InsufficientFunds, InvalidInput
from flash.domain.shared.identifiers import EntityId
from flash.domain.shared.money import Money

_MIN_AUTH_ID = 8


@dataclass(frozen=True, slots=True)
class AuthorizationDecision:
    authorization_id: str
    decision: str  # "APPROVED" | "DECLINED"
    reason: str | None
    amount_minor: int
    currency: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "authorization_id": self.authorization_id,
            "decision": self.decision,
            "reason": self.reason,
            "amount_minor": self.amount_minor,
            "currency": self.currency,
        }


@dataclass(frozen=True, slots=True)
class SettlementResult:
    authorization_id: str
    status: str
    amount_minor: int
    currency: str
    wallet_available_after_minor: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "authorization_id": self.authorization_id,
            "status": self.status,
            "amount_minor": self.amount_minor,
            "currency": self.currency,
            "wallet_available_after_minor": self.wallet_available_after_minor,
        }


def _start_of_day(now: datetime) -> datetime:
    return now.replace(hour=0, minute=0, second=0, microsecond=0)


def _start_of_month(now: datetime) -> datetime:
    return now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)


def _client_and_scheme(uow: WorkUnitOfWork, *, owner_ref: str, currency: Any) -> tuple[Any, Any]:
    client = uow.ledger.ensure_account(
        account_type=AccountType.CLIENT_LIABILITY, currency=currency, owner_ref=owner_ref
    )
    scheme = uow.ledger.ensure_account(
        account_type=AccountType.CARD_SCHEME_SUSPENSE, currency=currency
    )
    return client, scheme


# ============================================================== autoriser
@dataclass(frozen=True, slots=True)
class AuthorizeCardPaymentCommand(Command):
    authorization_id: str
    pan_token: str
    amount_minor: int
    channel: str
    merchant_name: str | None = None


class AuthorizeCardPayment(UseCase[AuthorizeCardPaymentCommand, AuthorizationDecision]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: AuthorizeCardPaymentCommand) -> AuthorizationDecision:
        if len(command.authorization_id) < _MIN_AUTH_ID:
            raise InvalidInput("authorization_id trop court (8 caractères minimum).")
        if command.amount_minor <= 0:
            raise InvalidInput("Le montant doit être strictement positif.")
        try:
            channel = CardChannel(command.channel)
        except ValueError as exc:
            raise InvalidInput("Canal de carte inconnu.") from exc

        now = self._services.clock.now()
        auth_id = self._services.ids.new_id()
        captured: dict[str, Any] = {}

        def work(uow: WorkUnitOfWork) -> None:
            existing = uow.card_authorizations.get_by_authorization_id(command.authorization_id)
            if existing is not None:
                captured.update(
                    decision="APPROVED" if existing.is_open else "DECLINED",
                    reason=existing.decline_reason,
                    amount=existing.amount.amount_minor,
                    currency=existing.currency_code,
                )
                if existing.status.value in ("CAPTURED", "REVERSED", "REFUNDED"):
                    captured["decision"] = "APPROVED"
                return

            card = uow.cards.get_by_pan_token(command.pan_token)
            if card is None:
                captured.update(
                    decision="DECLINED",
                    reason="CARD_NOT_FOUND",
                    amount=command.amount_minor,
                    currency="",
                )
                return

            amount = Money(command.amount_minor, card.currency)
            spent_today = uow.card_authorizations.total_spent_since(card.id, _start_of_day(now))
            spent_month = uow.card_authorizations.total_spent_since(card.id, _start_of_month(now))

            # Le montant est déjà validé (> 0) et dans la devise de la carte : seules des
            # décisions de refus métier peuvent remonter ici.
            reason: str | None = None
            try:
                card.ensure_can_authorize(
                    amount=amount,
                    channel=channel,
                    spent_today=spent_today,
                    spent_month=spent_month,
                )
            except DomainError as exc:
                reason = exc.code

            if reason is None:
                wallet = uow.wallets.get_for_update(EntityId(str(card.wallet_id)))
                try:
                    wallet.reserve(amount, now)
                except InsufficientFunds:
                    reason = "INSUFFICIENT_FUNDS"
                else:
                    auth = CardAuthorization.authorize(
                        auth_id=auth_id,
                        card_id=card.id,
                        wallet_id=EntityId(str(card.wallet_id)),
                        user_id=card.user_id,
                        authorization_id=command.authorization_id,
                        amount=amount,
                        channel=channel,
                        now=now,
                        merchant_name=command.merchant_name,
                    )
                    uow.card_authorizations.add(auth)
                    uow.wallets.save(wallet)
                    captured.update(
                        decision="APPROVED",
                        reason=None,
                        amount=amount.amount_minor,
                        currency=card.currency.code,
                    )

            if reason is not None:
                auth = CardAuthorization.declined(
                    auth_id=auth_id,
                    card_id=card.id,
                    wallet_id=EntityId(str(card.wallet_id)),
                    user_id=card.user_id,
                    authorization_id=command.authorization_id,
                    amount=amount,
                    channel=channel,
                    reason=reason,
                    now=now,
                    merchant_name=command.merchant_name,
                )
                uow.card_authorizations.add(auth)
                captured.update(
                    decision="DECLINED",
                    reason=reason,
                    amount=amount.amount_minor,
                    currency=card.currency.code,
                )

        execute_in_uow(self._services.uow, self._services.events, work)
        return AuthorizationDecision(
            authorization_id=command.authorization_id,
            decision=captured["decision"],
            reason=captured["reason"],
            amount_minor=captured["amount"],
            currency=captured["currency"],
        )


# ============================================================== capturer / annuler / rembourser
@dataclass(frozen=True, slots=True)
class CaptureCardPaymentCommand(Command):
    authorization_id: str
    amount_minor: int | None = None


@dataclass(frozen=True, slots=True)
class ReverseCardAuthorizationCommand(Command):
    authorization_id: str


@dataclass(frozen=True, slots=True)
class RefundCardPaymentCommand(Command):
    authorization_id: str


def _load_auth(uow: WorkUnitOfWork, authorization_id: str) -> CardAuthorization:
    try:
        return uow.card_authorizations.get_for_update_by_authorization_id(authorization_id)
    except KeyError as exc:
        raise InvalidInput("Autorisation introuvable.") from exc


class CaptureCardPayment(UseCase[CaptureCardPaymentCommand, SettlementResult]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: CaptureCardPaymentCommand) -> SettlementResult:
        now = self._services.clock.now()
        txn_id = self._services.ids.new_id()
        captured: dict[str, Any] = {}

        def work(uow: WorkUnitOfWork) -> None:
            auth = _load_auth(uow, command.authorization_id)
            if auth.status.value == "CAPTURED":  # rejeu
                wallet = uow.wallets.get(EntityId(str(auth.wallet_id)))
                assert wallet is not None
                captured.update(
                    status="CAPTURED",
                    amount=auth.captured_minor or 0,
                    currency=auth.currency_code,
                    available_after=wallet.available.amount_minor,
                )
                return
            amount = (
                Money(command.amount_minor, auth.amount.currency)
                if command.amount_minor is not None
                else auth.amount
            )
            wallet = uow.wallets.get_for_update(EntityId(str(auth.wallet_id)))
            client, scheme = _client_and_scheme(
                uow, owner_ref=str(wallet.user_id), currency=wallet.currency
            )
            uow.ledger.add(
                LedgerTransaction.card_capture(
                    id=txn_id,
                    occurred_at=now,
                    reference=f"CARDCAP-{auth.authorization_id}",
                    client_account_id=client,
                    client_wallet_id=EntityId(str(wallet.id)),
                    card_scheme_account_id=scheme,
                    amount=amount,
                    metadata={
                        "card_last4": _last4(uow, auth.card_id),
                        "merchant_name": auth.merchant_name,
                        "amount_minor": amount.amount_minor,
                    },
                )
            )
            wallet.settle_reservation(amount, now)
            if amount < auth.amount:
                wallet.release(auth.amount - amount, now)
            auth.capture(amount=amount, ledger_transaction_id=txn_id, now=now)
            uow.wallets.save(wallet)
            uow.card_authorizations.save(auth)
            captured.update(
                status="CAPTURED",
                amount=amount.amount_minor,
                currency=wallet.currency.code,
                available_after=wallet.available.amount_minor,
            )

        execute_in_uow(self._services.uow, self._services.events, work)
        return SettlementResult(
            authorization_id=command.authorization_id,
            status=captured["status"],
            amount_minor=captured["amount"],
            currency=captured["currency"],
            wallet_available_after_minor=captured["available_after"],
        )


class ReverseCardAuthorization(UseCase[ReverseCardAuthorizationCommand, SettlementResult]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: ReverseCardAuthorizationCommand) -> SettlementResult:
        now = self._services.clock.now()
        captured: dict[str, Any] = {}

        def work(uow: WorkUnitOfWork) -> None:
            auth = _load_auth(uow, command.authorization_id)
            wallet = uow.wallets.get_for_update(EntityId(str(auth.wallet_id)))
            if auth.status.value == "REVERSED":  # rejeu
                captured.update(
                    amount=auth.amount.amount_minor,
                    currency=auth.currency_code,
                    available_after=wallet.available.amount_minor,
                )
                return
            auth.reverse(now)
            wallet.release(auth.amount, now)
            uow.wallets.save(wallet)
            uow.card_authorizations.save(auth)
            captured.update(
                amount=auth.amount.amount_minor,
                currency=wallet.currency.code,
                available_after=wallet.available.amount_minor,
            )

        execute_in_uow(self._services.uow, self._services.events, work)
        return SettlementResult(
            authorization_id=command.authorization_id,
            status="REVERSED",
            amount_minor=captured["amount"],
            currency=captured["currency"],
            wallet_available_after_minor=captured["available_after"],
        )


class RefundCardPayment(UseCase[RefundCardPaymentCommand, SettlementResult]):
    def __init__(self, *, services: AppServices) -> None:
        self._services = services

    def execute(self, command: RefundCardPaymentCommand) -> SettlementResult:
        now = self._services.clock.now()
        txn_id = self._services.ids.new_id()
        captured: dict[str, Any] = {}

        def work(uow: WorkUnitOfWork) -> None:
            auth = _load_auth(uow, command.authorization_id)
            wallet = uow.wallets.get_for_update(EntityId(str(auth.wallet_id)))
            if auth.status.value == "REFUNDED":  # rejeu
                captured.update(
                    amount=auth.captured_minor or 0,
                    currency=auth.currency_code,
                    available_after=wallet.available.amount_minor,
                )
                return
            client, scheme = _client_and_scheme(
                uow, owner_ref=str(wallet.user_id), currency=wallet.currency
            )
            refunded = auth.refund(ledger_transaction_id=txn_id, now=now)
            uow.ledger.add(
                LedgerTransaction.card_refund(
                    id=txn_id,
                    occurred_at=now,
                    reference=f"CARDREF-{auth.authorization_id}",
                    client_account_id=client,
                    client_wallet_id=EntityId(str(wallet.id)),
                    card_scheme_account_id=scheme,
                    amount=refunded,
                    metadata={
                        "card_last4": _last4(uow, auth.card_id),
                        "merchant_name": auth.merchant_name,
                        "amount_minor": refunded.amount_minor,
                    },
                )
            )
            wallet.credit(refunded, now)
            uow.wallets.save(wallet)
            uow.card_authorizations.save(auth)
            captured.update(
                amount=refunded.amount_minor,
                currency=wallet.currency.code,
                available_after=wallet.available.amount_minor,
            )

        execute_in_uow(self._services.uow, self._services.events, work)
        return SettlementResult(
            authorization_id=command.authorization_id,
            status="REFUNDED",
            amount_minor=captured["amount"],
            currency=captured["currency"],
            wallet_available_after_minor=captured["available_after"],
        )


def _last4(uow: WorkUnitOfWork, card_id: EntityId) -> str | None:
    card = uow.cards.get(card_id)
    return card.last4 if card is not None else None


__all__ = [
    "AuthorizationDecision",
    "AuthorizeCardPayment",
    "AuthorizeCardPaymentCommand",
    "CaptureCardPayment",
    "CaptureCardPaymentCommand",
    "RefundCardPayment",
    "RefundCardPaymentCommand",
    "ReverseCardAuthorization",
    "ReverseCardAuthorizationCommand",
    "SettlementResult",
]
