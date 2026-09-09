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
    pin_hash: Mapped[str] = mapped_column(String(255), nullable=False)
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
    vaulted_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    saved_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id", "currency"),
        CheckConstraint("available_minor >= 0", name="available_non_negative"),
        CheckConstraint("reserved_minor >= 0", name="reserved_non_negative"),
        CheckConstraint("vaulted_minor >= 0", name="vaulted_non_negative"),
        CheckConstraint("saved_minor >= 0", name="saved_non_negative"),
    )


class VaultPocketModel(Base):
    """Une poche du coffre. Le coffre lui-même n'a pas de table : c'est l'ensemble des
    poches d'un portefeuille (``sum(balance_minor) == wallets.vaulted_minor``)."""

    __tablename__ = "vault_pockets"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    vault_id: Mapped[str] = mapped_column(_UUID, nullable=False)
    wallet_id: Mapped[str] = mapped_column(
        ForeignKey("wallets.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    currency: Mapped[str] = mapped_column(_CCY, nullable=False)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    balance_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    goal_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    locked_until: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)

    __table_args__ = (
        CheckConstraint("balance_minor >= 0", name="pocket_balance_non_negative"),
        Index("ix_vault_pockets_wallet_id", "wallet_id"),
    )


class SavingsPlanModel(Base):
    __tablename__ = "savings_plans"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    wallet_id: Mapped[str] = mapped_column(
        ForeignKey("wallets.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    currency: Mapped[str] = mapped_column(_CCY, nullable=False)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    balance_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    annual_rate_bps: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    frequency: Mapped[str] = mapped_column(String(8), nullable=False, default="NONE")
    contribution_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    target_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    target_date: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    next_contribution_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    last_accrual_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    accrued_micro: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(8), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)

    __table_args__ = (
        CheckConstraint("balance_minor >= 0", name="plan_balance_non_negative"),
        CheckConstraint("accrued_micro >= 0", name="plan_accrued_non_negative"),
        Index("ix_savings_plans_user_id", "user_id"),
        Index(
            "ix_savings_plans_due",
            "next_contribution_at",
            postgresql_where=text("status = 'ACTIVE' AND next_contribution_at IS NOT NULL"),
        ),
    )


class CardModel(Base):
    __tablename__ = "cards"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    wallet_id: Mapped[str] = mapped_column(
        ForeignKey("wallets.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    currency: Mapped[str] = mapped_column(_CCY, nullable=False)
    network: Mapped[str] = mapped_column(String(12), nullable=False)
    pan_token: Mapped[str] = mapped_column(String(64), nullable=False)
    last4: Mapped[str] = mapped_column(String(4), nullable=False)
    expiry_month: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    expiry_year: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(8), nullable=False, default="ACTIVE")
    daily_limit_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    monthly_limit_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    channels: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("pan_token"),
        CheckConstraint("daily_limit_minor > 0", name="card_daily_limit_positive"),
        CheckConstraint("monthly_limit_minor > 0", name="card_monthly_limit_positive"),
        Index("ix_cards_user_id", "user_id"),
    )


class CardAuthorizationModel(Base):
    __tablename__ = "card_authorizations"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    card_id: Mapped[str] = mapped_column(
        ForeignKey("cards.id", ondelete="RESTRICT"), nullable=False
    )
    wallet_id: Mapped[str] = mapped_column(_UUID, nullable=False)
    user_id: Mapped[str] = mapped_column(_UUID, nullable=False)
    authorization_id: Mapped[str] = mapped_column(String(80), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(_CCY, nullable=False)
    channel: Mapped[str] = mapped_column(String(12), nullable=False)
    merchant_name: Mapped[str | None] = mapped_column(String(140), nullable=True)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    decline_reason: Mapped[str | None] = mapped_column(String(40), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    captured_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    ledger_transaction_id: Mapped[str | None] = mapped_column(_UUID, nullable=True)

    __table_args__ = (
        UniqueConstraint("authorization_id"),
        CheckConstraint("amount_minor > 0", name="card_auth_amount_positive"),
        Index("ix_card_authorizations_card_recent", "card_id", "created_at"),
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


class AgentModel(Base):
    __tablename__ = "agents"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    currency: Mapped[str] = mapped_column(_CCY, nullable=False)
    float_available_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    float_cap_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    commission_bps: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id"),
        CheckConstraint("float_available_minor >= 0", name="float_non_negative"),
        CheckConstraint("float_available_minor <= float_cap_minor", name="float_within_cap"),
    )


class CashOrderModel(Base):
    __tablename__ = "cash_orders"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    type: Mapped[str] = mapped_column(String(12), nullable=False)
    client_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    agent_id: Mapped[str | None] = mapped_column(_UUID, nullable=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fee_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(_CCY, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    code_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    expires_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    ledger_transaction_id: Mapped[str | None] = mapped_column(_UUID, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)

    __table_args__ = (
        Index("ix_cash_orders_client_id", "client_id"),
        Index(
            "ux_cash_orders_pending_code",
            "code_hash",
            unique=True,
            postgresql_where=text("status = 'INITIATED' AND code_hash IS NOT NULL"),
        ),
    )


class MerchantModel(Base):
    __tablename__ = "merchants"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    display_name: Mapped[str] = mapped_column(String(120), nullable=False)
    category: Mapped[str] = mapped_column(String(48), nullable=False, default="GENERAL")
    currency: Mapped[str] = mapped_column(_CCY, nullable=False)
    fee_bps: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE")
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id"),
        CheckConstraint("fee_bps >= 0 AND fee_bps <= 1000", name="fee_bps_bounds"),
    )


class MerchantChargeModel(Base):
    __tablename__ = "merchant_charges"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    merchant_id: Mapped[str] = mapped_column(
        ForeignKey("merchants.id", ondelete="RESTRICT"), nullable=False
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(_CCY, nullable=False)
    reference: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    paid_by: Mapped[str | None] = mapped_column(_UUID, nullable=True)
    ledger_transaction_id: Mapped[str | None] = mapped_column(_UUID, nullable=True)

    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="amount_positive"),
        Index("ix_merchant_charges_merchant_id", "merchant_id"),
    )


class MerchantPaymentModel(Base):
    __tablename__ = "merchant_payments"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    payer_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    merchant_id: Mapped[str] = mapped_column(
        ForeignKey("merchants.id", ondelete="RESTRICT"), nullable=False
    )
    charge_id: Mapped[str | None] = mapped_column(_UUID, nullable=True)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fee_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(_CCY, nullable=False)
    reference: Mapped[str] = mapped_column(String(80), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    ledger_transaction_id: Mapped[str] = mapped_column(_UUID, nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)

    __table_args__ = (Index("ix_merchant_payments_merchant_id", "merchant_id"),)


class PaymentRequestModel(Base):
    __tablename__ = "payment_requests"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    requester_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    payer_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(_CCY, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    note: Mapped[str | None] = mapped_column(String(140), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    resulting_transfer_id: Mapped[str | None] = mapped_column(_UUID, nullable=True)

    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="amount_positive"),
        CheckConstraint("requester_id <> payer_id", name="not_self_request"),
        Index("ix_payment_requests_payer_id", "payer_id"),
        Index("ix_payment_requests_requester_id", "requester_id"),
    )


class KycCaseModel(Base):
    __tablename__ = "kyc_cases"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    target_tier: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    decided_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    reviewer_id: Mapped[str | None] = mapped_column(_UUID, nullable=True)
    decision_reason: Mapped[str | None] = mapped_column(Text, nullable=True)

    documents: Mapped[list[KycDocumentModel]] = relationship(
        back_populates="case",
        cascade="all, delete-orphan",
        order_by="KycDocumentModel.kind",
        lazy="selectin",
    )

    __table_args__ = (
        Index("ix_kyc_cases_user_id", "user_id"),
        Index(
            "ux_kyc_cases_one_pending_per_user",
            "user_id",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
        ),
    )


class KycDocumentModel(Base):
    __tablename__ = "kyc_documents"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    case_id: Mapped[str] = mapped_column(
        ForeignKey("kyc_cases.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    storage_key: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(64), nullable=False)
    byte_size: Mapped[int] = mapped_column(BigInteger, nullable=False)
    uploaded_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)

    case: Mapped[KycCaseModel] = relationship(back_populates="documents")

    __table_args__ = (UniqueConstraint("case_id", "kind"),)


class NotificationModel(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    title: Mapped[str] = mapped_column(String(140), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    read_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)

    __table_args__ = (
        Index("ix_notifications_user_recent", "user_id", "id"),
        Index(
            "ix_notifications_user_unread",
            "user_id",
            postgresql_where=text("read_at IS NULL"),
        ),
    )


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
    "AgentModel",
    "CardAuthorizationModel",
    "CardModel",
    "CashOrderModel",
    "IdempotencyKeyModel",
    "KycCaseModel",
    "KycDocumentModel",
    "LedgerAccountModel",
    "LedgerPostingModel",
    "LedgerTransactionModel",
    "MerchantChargeModel",
    "MerchantModel",
    "MerchantPaymentModel",
    "NotificationModel",
    "OutboxModel",
    "PaymentRequestModel",
    "PhoneNumberModel",
    "SavingsPlanModel",
    "UserModel",
    "VaultPocketModel",
    "WalletModel",
]
