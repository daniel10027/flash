"""Modèles ORM (SQLAlchemy 2) — schéma physique de Flash.

Séparés des entités de domaine. Montants stockés en ``BigInteger`` (unité mineure).
Les soldes de wallet sont maintenus dans ``wallets`` : cette table **est** la projection
de solde, recalculable depuis le ledger (job de réconciliation ``BE-045``).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    ForeignKey,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from flash.infrastructure.db.base import Base, TZDateTime

_UUID = String(36)
_CCY = String(3)
_COUNTRY = String(2)


class UserModel(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    country: Mapped[str] = mapped_column(_COUNTRY, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    kyc_tier: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)

    phone_numbers: Mapped[list[PhoneNumberModel]] = relationship(
        back_populates="user",
        cascade="all, delete-orphan",
        order_by="PhoneNumberModel.linked_at",
        lazy="selectin",
    )

    __table_args__ = (CheckConstraint("kyc_tier between 0 and 2", name="kyc_tier_range"),)


class PhoneNumberModel(Base):
    __tablename__ = "phone_numbers"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    msisdn: Mapped[str] = mapped_column(String(20), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    linked_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    verified_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)

    user: Mapped[UserModel] = relationship(back_populates="phone_numbers")

    __table_args__ = (
        UniqueConstraint("msisdn"),  # unicité globale du numéro
        Index("ix_phone_numbers_user_id", "user_id"),
    )


class WalletModel(Base):
    __tablename__ = "wallets"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    currency: Mapped[str] = mapped_column(_CCY, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    available_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    reserved_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "currency"),
        CheckConstraint("available_minor >= 0", name="available_non_negative"),
        CheckConstraint("reserved_minor >= 0", name="reserved_non_negative"),
    )


class LedgerAccountModel(Base):
    __tablename__ = "ledger_accounts"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    type: Mapped[str] = mapped_column(String(32), nullable=False)
    currency: Mapped[str] = mapped_column(_CCY, nullable=False)
    owner_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)

    __table_args__ = (
        Index(
            "ux_ledger_accounts_identity",
            "type",
            "currency",
            "owner_ref",
            unique=True,
            postgresql_nulls_not_distinct=True,
        ),
    )


class LedgerTransactionModel(Base):
    __tablename__ = "ledger_transactions"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    reference: Mapped[str] = mapped_column(String(64), nullable=False)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    tx_metadata: Mapped[dict[str, Any]] = mapped_column(
        "metadata", JSONB, nullable=False, default=dict
    )
    reverses_transaction_id: Mapped[str | None] = mapped_column(
        ForeignKey("ledger_transactions.id"), nullable=True
    )

    postings: Mapped[list[LedgerPostingModel]] = relationship(
        back_populates="transaction",
        cascade="all, delete-orphan",
        lazy="selectin",
    )

    __table_args__ = (Index("ix_ledger_transactions_reference", "reference"),)


class LedgerPostingModel(Base):
    __tablename__ = "ledger_postings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    transaction_id: Mapped[str] = mapped_column(
        ForeignKey("ledger_transactions.id", ondelete="CASCADE"), nullable=False
    )
    account_id: Mapped[str] = mapped_column(ForeignKey("ledger_accounts.id"), nullable=False)
    direction: Mapped[str] = mapped_column(String(6), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(_CCY, nullable=False)
    wallet_id: Mapped[str | None] = mapped_column(_UUID, nullable=True)
    analytic: Mapped[str | None] = mapped_column(String(64), nullable=True)

    transaction: Mapped[LedgerTransactionModel] = relationship(back_populates="postings")

    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="amount_positive"),
        CheckConstraint("direction in ('DEBIT','CREDIT')", name="direction_valid"),
        Index("ix_ledger_postings_wallet_id", "wallet_id"),
        Index("ix_ledger_postings_account_id", "account_id"),
    )


class IdempotencyKeyModel(Base):
    __tablename__ = "idempotency_keys"

    key: Mapped[str] = mapped_column(String(320), primary_key=True)
    result: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)

    __table_args__ = (Index("ix_idempotency_keys_expires_at", "expires_at"),)


class OutboxModel(Base):
    __tablename__ = "outbox"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    event_name: Mapped[str] = mapped_column(String(64), nullable=False)
    aggregate_id: Mapped[str] = mapped_column(String(64), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    occurred_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    published_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)

    __table_args__ = (
        Index(
            "ix_outbox_unpublished",
            "created_at",
            postgresql_where=text("published_at IS NULL"),
        ),
    )


__all__ = [
    "IdempotencyKeyModel",
    "LedgerAccountModel",
    "LedgerPostingModel",
    "LedgerTransactionModel",
    "OutboxModel",
    "PhoneNumberModel",
    "UserModel",
    "WalletModel",
]
