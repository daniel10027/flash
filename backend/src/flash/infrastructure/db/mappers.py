"""Conversions ORM ↔ domaine.

Un sens (``*_to_domain``) reconstruit un agrégat pur à partir des lignes. L'autre
(``*_to_model``) produit un modèle ORM prêt à être ``merge`` dans une session. Aucune
règle métier ici : uniquement du recopiage de champs.
"""

from __future__ import annotations

from uuid import NAMESPACE_URL, uuid5

from flash.domain.identity.kyc import KycTier
from flash.domain.identity.user import PhoneNumber, User, UserStatus
from flash.domain.ledger.chart import Direction
from flash.domain.ledger.transaction import LedgerTransaction, Posting, TransactionKind
from flash.domain.shared.identifiers import CountryCode, EntityId, Msisdn
from flash.domain.shared.money import Currency, Money
from flash.domain.wallet.wallet import Wallet, WalletStatus
from flash.infrastructure.db.models import (
    LedgerPostingModel,
    LedgerTransactionModel,
    PhoneNumberModel,
    UserModel,
    WalletModel,
)

# --------------------------------------------------------------------- identité


def _phone_number_id(user_id: str, msisdn: str) -> str:
    """Identifiant déterministe d'un numéro : stable d'une écriture à l'autre (upsert)."""
    return str(uuid5(NAMESPACE_URL, f"flash:phone:{user_id}:{msisdn}"))


def user_to_domain(model: UserModel) -> User:
    phones = [
        PhoneNumber(
            msisdn=Msisdn(p.msisdn),
            linked_at=p.linked_at,
            is_primary=p.is_primary,
            verified_at=p.verified_at,
        )
        for p in sorted(model.phone_numbers, key=lambda p: p.linked_at)
    ]
    return User(
        id=EntityId(model.id),
        country=CountryCode(model.country),
        status=UserStatus(model.status),
        kyc_tier=KycTier(model.kyc_tier),
        phone_numbers=phones,
        created_at=model.created_at,
    )


def user_to_model(user: User) -> UserModel:
    return UserModel(
        id=str(user.id),
        country=user.country.value,
        status=user.status.value,
        kyc_tier=int(user.kyc_tier),
        created_at=user.created_at,
        phone_numbers=[
            PhoneNumberModel(
                id=_phone_number_id(str(user.id), p.msisdn.value),
                user_id=str(user.id),
                msisdn=p.msisdn.value,
                is_primary=p.is_primary,
                linked_at=p.linked_at,
                verified_at=p.verified_at,
            )
            for p in user.phone_numbers
        ],
    )


# ----------------------------------------------------------------------- wallet


def wallet_to_domain(model: WalletModel) -> Wallet:
    currency = Currency.of(model.currency)
    return Wallet(
        id=EntityId(model.id),
        user_id=EntityId(model.user_id),
        currency=currency,
        available=Money(model.available_minor, currency),
        reserved=Money(model.reserved_minor, currency),
        created_at=model.created_at,
        status=WalletStatus(model.status),
    )


def wallet_to_model(wallet: Wallet) -> WalletModel:
    return WalletModel(
        id=str(wallet.id),
        user_id=str(wallet.user_id),
        currency=wallet.currency.code,
        status=wallet.status.value,
        available_minor=wallet.available.amount_minor,
        reserved_minor=wallet.reserved.amount_minor,
        created_at=wallet.created_at,
    )


# ----------------------------------------------------------------------- ledger


def ledger_transaction_to_model(txn: LedgerTransaction) -> LedgerTransactionModel:
    return LedgerTransactionModel(
        id=str(txn.id),
        kind=txn.kind.value,
        occurred_at=txn.occurred_at,
        reference=txn.reference,
        reason=txn.reason,
        tx_metadata=dict(txn.metadata),
        reverses_transaction_id=(
            str(txn.reverses_transaction_id) if txn.reverses_transaction_id else None
        ),
        postings=[
            LedgerPostingModel(
                account_id=str(p.account_id),
                direction=p.direction.value,
                amount_minor=p.amount.amount_minor,
                currency=p.amount.currency.code,
                wallet_id=str(p.wallet_id) if p.wallet_id else None,
                analytic=p.analytic,
            )
            for p in txn.postings
        ],
    )


def ledger_transaction_to_domain(model: LedgerTransactionModel) -> LedgerTransaction:
    postings = tuple(
        Posting(
            account_id=EntityId(p.account_id),
            direction=Direction(p.direction),
            amount=Money(p.amount_minor, Currency.of(p.currency)),
            wallet_id=EntityId(p.wallet_id) if p.wallet_id else None,
            analytic=p.analytic,
        )
        for p in model.postings
    )
    return LedgerTransaction(
        id=EntityId(model.id),
        kind=TransactionKind(model.kind),
        postings=postings,
        occurred_at=model.occurred_at,
        reference=model.reference,
        reason=model.reason,
        metadata=dict(model.tx_metadata),
        reverses_transaction_id=(
            EntityId(model.reverses_transaction_id) if model.reverses_transaction_id else None
        ),
    )


__all__ = [
    "ledger_transaction_to_domain",
    "ledger_transaction_to_model",
    "user_to_domain",
    "user_to_model",
    "wallet_to_domain",
    "wallet_to_model",
]
