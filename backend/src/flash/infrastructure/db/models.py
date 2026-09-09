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


class CountryModel(Base):
    __tablename__ = "countries"

    code: Mapped[str] = mapped_column(_COUNTRY, primary_key=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    currency: Mapped[str] = mapped_column(_CCY, nullable=False)
    dialing_code: Mapped[str] = mapped_column(String(6), nullable=False)
    timezone: Mapped[str] = mapped_column(String(48), nullable=False, default="UTC")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    operators: Mapped[list[OperatorModel]] = relationship(
        back_populates="country",
        cascade="all, delete-orphan",
        order_by="OperatorModel.code",
        lazy="selectin",
    )


class OperatorModel(Base):
    __tablename__ = "operators"

    code: Mapped[str] = mapped_column(String(32), primary_key=True)
    country_code: Mapped[str] = mapped_column(
        ForeignKey("countries.code", ondelete="CASCADE"), nullable=False
    )
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    msisdn_prefixes: Mapped[str] = mapped_column(String(200), nullable=False, default="")
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    country: Mapped[CountryModel] = relationship(back_populates="operators")

    __table_args__ = (Index("ix_operators_country_code", "country_code"),)


class PricingRuleModel(Base):
    """Grille tarifaire éditable (BE-062) — une règle par couple (pays, opération)."""

    __tablename__ = "pricing_rules"

    country_code: Mapped[str] = mapped_column(_COUNTRY, primary_key=True)
    operation: Mapped[str] = mapped_column(String(32), primary_key=True)
    currency: Mapped[str] = mapped_column(_CCY, nullable=False)
    percent_bps: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    fixed_fee_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    min_fee_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    max_fee_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    rounding: Mapped[str] = mapped_column(String(16), nullable=False, default="HALF_UP")
    updated_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)

    __table_args__ = (
        CheckConstraint("percent_bps between 0 and 10000", name="percent_bps_range"),
    )


class LimitRuleModel(Base):
    """Plafonds éditables (BE-062) — une règle par (pays, palier KYC, opération)."""

    __tablename__ = "limit_rules"

    country_code: Mapped[str] = mapped_column(_COUNTRY, primary_key=True)
    kyc_tier: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    operation: Mapped[str] = mapped_column(String(32), primary_key=True)
    currency: Mapped[str] = mapped_column(_CCY, nullable=False)
    per_tx_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    daily_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    monthly_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    balance_max_minor: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)

    __table_args__ = (
        CheckConstraint("kyc_tier between 0 and 2", name="kyc_tier_range"),
    )


class AuditEntryModel(Base):
    __tablename__ = "audit_entries"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    sequence: Mapped[int] = mapped_column(BigInteger, nullable=False)
    actor: Mapped[str] = mapped_column(String(64), nullable=False)
    role: Mapped[str] = mapped_column(String(24), nullable=False)
    action: Mapped[str] = mapped_column(String(48), nullable=False)
    resource_type: Mapped[str] = mapped_column(String(48), nullable=False)
    resource_id: Mapped[str] = mapped_column(String(64), nullable=False)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    prev_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    entry_hash: Mapped[str] = mapped_column(String(64), nullable=False)

    __table_args__ = (
        UniqueConstraint("sequence"),
        UniqueConstraint("entry_hash"),
        Index("ix_audit_entries_sequence", "sequence"),
    )


class OperatorTransferModel(Base):
    __tablename__ = "operator_transfers"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    wallet_id: Mapped[str] = mapped_column(_UUID, nullable=False)
    operator: Mapped[str] = mapped_column(String(32), nullable=False)
    direction: Mapped[str] = mapped_column(String(8), nullable=False)
    msisdn: Mapped[str] = mapped_column(String(20), nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fee_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    currency: Mapped[str] = mapped_column(_CCY, nullable=False)
    reference: Mapped[str] = mapped_column(String(64), nullable=False)
    external_ref: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    failure_reason: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    ledger_transaction_id: Mapped[str | None] = mapped_column(_UUID, nullable=True)

    __table_args__ = (
        UniqueConstraint("reference"),
        CheckConstraint("amount_minor > 0", name="operator_transfer_amount_positive"),
        Index("ix_operator_transfers_user_id", "user_id"),
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
    parent_agent_id: Mapped[str | None] = mapped_column(_UUID, nullable=True)
    commission_earned_minor: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=0
    )
    commission_paid_minor: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id"),
        CheckConstraint("float_available_minor >= 0", name="float_non_negative"),
        CheckConstraint("float_available_minor <= float_cap_minor", name="float_within_cap"),
        CheckConstraint(
            "commission_paid_minor <= commission_earned_minor", name="commission_paid_le_earned"
        ),
        Index("ix_agents_parent_agent_id", "parent_agent_id"),
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
    settlement_frequency: Mapped[str] = mapped_column(
        String(8), nullable=False, default="MANUAL"
    )
    bank_holder: Mapped[str | None] = mapped_column(String(120), nullable=True)
    bank_iban: Mapped[str | None] = mapped_column(String(40), nullable=True)
    bank_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    next_settlement_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    last_settlement_id: Mapped[str | None] = mapped_column(_UUID, nullable=True)
    kyb_status: Mapped[str] = mapped_column(String(10), nullable=False, default="PENDING")
    kyb_reviewed_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    kyb_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    webhook_url: Mapped[str | None] = mapped_column(String(300), nullable=True)
    webhook_secret: Mapped[str | None] = mapped_column(String(128), nullable=True)
    channel_fees: Mapped[dict[str, int]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)

    __table_args__ = (
        UniqueConstraint("user_id"),
        CheckConstraint("fee_bps >= 0 AND fee_bps <= 1000", name="fee_bps_bounds"),
        Index(
            "ix_merchants_settlement_due",
            "next_settlement_at",
            postgresql_where=text(
                "status = 'ACTIVE' AND next_settlement_at IS NOT NULL AND bank_iban IS NOT NULL"
            ),
        ),
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
    sub_account_id: Mapped[str | None] = mapped_column(_UUID, nullable=True)
    channel: Mapped[str] = mapped_column(String(8), nullable=False, default="QR")

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
    settlement_id: Mapped[str | None] = mapped_column(_UUID, nullable=True)
    sub_account_id: Mapped[str | None] = mapped_column(_UUID, nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)

    __table_args__ = (
        Index("ix_merchant_payments_merchant_id", "merchant_id"),
        Index("ix_merchant_payments_settlement_id", "settlement_id"),
        Index("ix_merchant_payments_sub_account_id", "sub_account_id"),
    )


class MerchantSubAccountModel(Base):
    __tablename__ = "merchant_sub_accounts"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    merchant_id: Mapped[str] = mapped_column(
        ForeignKey("merchants.id", ondelete="CASCADE"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(12), nullable=False)
    label: Mapped[str] = mapped_column(String(60), nullable=False)
    external_ref: Mapped[str | None] = mapped_column(String(40), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)

    __table_args__ = (Index("ix_merchant_sub_accounts_merchant_id", "merchant_id"),)


class MerchantSettlementModel(Base):
    __tablename__ = "merchant_settlements"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    merchant_id: Mapped[str] = mapped_column(
        ForeignKey("merchants.id", ondelete="RESTRICT"), nullable=False
    )
    user_id: Mapped[str] = mapped_column(_UUID, nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(_CCY, nullable=False)
    payment_count: Mapped[int] = mapped_column(BigInteger, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False)
    bank_reference: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_reason: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    settled_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    ledger_transaction_id: Mapped[str | None] = mapped_column(_UUID, nullable=True)

    __table_args__ = (
        CheckConstraint("amount_minor > 0", name="merchant_settlement_amount_positive"),
        Index("ix_merchant_settlements_merchant_id", "merchant_id"),
    )


class MerchantApiKeyModel(Base):
    __tablename__ = "merchant_api_keys"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    merchant_id: Mapped[str] = mapped_column(
        ForeignKey("merchants.id", ondelete="RESTRICT"), nullable=False
    )
    prefix: Mapped[str] = mapped_column(String(16), nullable=False, unique=True)
    secret_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    label: Mapped[str] = mapped_column(String(60), nullable=False, default="sans nom")
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    last_used_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)

    __table_args__ = (Index("ix_merchant_api_keys_merchant_id", "merchant_id"),)


class MerchantWebhookDeliveryModel(Base):
    __tablename__ = "merchant_webhook_deliveries"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    merchant_id: Mapped[str] = mapped_column(
        ForeignKey("merchants.id", ondelete="RESTRICT"), nullable=False
    )
    source_id: Mapped[str] = mapped_column(_UUID, nullable=False)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="PENDING")
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    next_attempt_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    delivered_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(String(200), nullable=True)

    __table_args__ = (
        UniqueConstraint("event_type", "source_id", name="uq_merchant_webhook_source"),
        Index(
            "ix_merchant_webhook_deliveries_due",
            "next_attempt_at",
            postgresql_where=text("status = 'PENDING'"),
        ),
    )


class ComplianceAlertModel(Base):
    __tablename__ = "compliance_alerts"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="OPEN")
    score: Mapped[int] = mapped_column(SmallInteger, nullable=False, default=0)
    detail: Mapped[dict[str, Any]] = mapped_column(JSONB, nullable=False, default=dict)
    window_key: Mapped[str] = mapped_column(String(80), nullable=False)
    reviewed_by: Mapped[str | None] = mapped_column(String(80), nullable=True)
    resolution_note: Mapped[str | None] = mapped_column(String(500), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    resolved_at: Mapped[datetime | None] = mapped_column(TZDateTime, nullable=True)

    __table_args__ = (
        UniqueConstraint("user_id", "kind", "window_key", name="uq_compliance_alert_window"),
        Index("ix_compliance_alerts_status", "status"),
        Index("ix_compliance_alerts_created_at", "created_at"),
    )


class SupportNoteModel(Base):
    __tablename__ = "support_notes"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    subject_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    author: Mapped[str] = mapped_column(String(80), nullable=False)
    body: Mapped[str] = mapped_column(String(2000), nullable=False)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)

    __table_args__ = (Index("ix_support_notes_subject_user_id", "subject_user_id"),)


class SupportTicketModel(Base):
    __tablename__ = "support_tickets"

    id: Mapped[str] = mapped_column(_UUID, primary_key=True)
    subject_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"), nullable=False
    )
    opened_by: Mapped[str] = mapped_column(String(80), nullable=False)
    subject: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="OPEN")
    last_actor: Mapped[str | None] = mapped_column(String(80), nullable=True)
    created_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(TZDateTime, nullable=False)

    __table_args__ = (
        Index("ix_support_tickets_subject_user_id", "subject_user_id"),
        Index("ix_support_tickets_status", "status"),
    )


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
    "AuditEntryModel",
    "CardAuthorizationModel",
    "CardModel",
    "CashOrderModel",
    "ComplianceAlertModel",
    "CountryModel",
    "IdempotencyKeyModel",
    "KycCaseModel",
    "KycDocumentModel",
    "LedgerAccountModel",
    "LedgerPostingModel",
    "LedgerTransactionModel",
    "LimitRuleModel",
    "MerchantApiKeyModel",
    "MerchantChargeModel",
    "MerchantModel",
    "MerchantPaymentModel",
    "MerchantSettlementModel",
    "MerchantSubAccountModel",
    "MerchantWebhookDeliveryModel",
    "NotificationModel",
    "OperatorModel",
    "OperatorTransferModel",
    "OutboxModel",
    "PaymentRequestModel",
    "PhoneNumberModel",
    "PricingRuleModel",
    "SavingsPlanModel",
    "SupportNoteModel",
    "SupportTicketModel",
    "UserModel",
    "VaultPocketModel",
    "WalletModel",
]
