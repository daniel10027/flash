"""marchands : sous-comptes caisses/employés & frais négociés par canal

Revision ID: d1e4b7a2f9c6
Revises: c3f5a9e0d182
Create Date: 2026-09-09 17:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d1e4b7a2f9c6"
down_revision: str | None = "c3f5a9e0d182"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "merchants",
        sa.Column(
            "channel_fees",
            postgresql.JSONB(astext_type=sa.Text()),
            nullable=False,
            server_default=sa.text("'{}'::jsonb"),
        ),
    )
    op.add_column(
        "merchant_charges",
        sa.Column("sub_account_id", sa.String(length=36), nullable=True),
    )
    op.add_column(
        "merchant_charges",
        sa.Column(
            "channel",
            sa.String(length=8),
            nullable=False,
            server_default="QR",
        ),
    )
    op.add_column(
        "merchant_payments",
        sa.Column("sub_account_id", sa.String(length=36), nullable=True),
    )
    op.create_index(
        "ix_merchant_payments_sub_account_id",
        "merchant_payments",
        ["sub_account_id"],
        unique=False,
    )
    op.create_table(
        "merchant_sub_accounts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("merchant_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=12), nullable=False),
        sa.Column("label", sa.String(length=60), nullable=False),
        sa.Column("external_ref", sa.String(length=40), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["merchant_id"],
            ["merchants.id"],
            name=op.f("fk_merchant_sub_accounts_merchant_id_merchants"),
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_merchant_sub_accounts")),
    )
    op.create_index(
        "ix_merchant_sub_accounts_merchant_id",
        "merchant_sub_accounts",
        ["merchant_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        "ix_merchant_sub_accounts_merchant_id", table_name="merchant_sub_accounts"
    )
    op.drop_table("merchant_sub_accounts")
    op.drop_index(
        "ix_merchant_payments_sub_account_id", table_name="merchant_payments"
    )
    op.drop_column("merchant_payments", "sub_account_id")
    op.drop_column("merchant_charges", "channel")
    op.drop_column("merchant_charges", "sub_account_id")
    op.drop_column("merchants", "channel_fees")
