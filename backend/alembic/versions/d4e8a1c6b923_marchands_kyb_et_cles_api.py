"""marchands : vérification KYB + clés d'API

Revision ID: d4e8a1c6b923
Revises: c7d2f4a91b38
Create Date: 2026-09-09 11:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "d4e8a1c6b923"
down_revision: str | None = "c7d2f4a91b38"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "merchants",
        sa.Column(
            "kyb_status", sa.String(length=10), nullable=False, server_default="PENDING"
        ),
    )
    op.add_column(
        "merchants", sa.Column("kyb_reviewed_at", sa.DateTime(timezone=True), nullable=True)
    )
    op.add_column("merchants", sa.Column("kyb_reason", sa.String(length=200), nullable=True))

    op.create_table(
        "merchant_api_keys",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("merchant_id", sa.String(length=36), nullable=False),
        sa.Column("prefix", sa.String(length=16), nullable=False),
        sa.Column("secret_hash", sa.String(length=64), nullable=False),
        sa.Column("label", sa.String(length=60), nullable=False, server_default="sans nom"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["merchant_id"],
            ["merchants.id"],
            name=op.f("fk_merchant_api_keys_merchant_id_merchants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_merchant_api_keys")),
        sa.UniqueConstraint("prefix", name=op.f("uq_merchant_api_keys_prefix")),
    )
    op.create_index(
        "ix_merchant_api_keys_merchant_id", "merchant_api_keys", ["merchant_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_merchant_api_keys_merchant_id", table_name="merchant_api_keys")
    op.drop_table("merchant_api_keys")
    op.drop_column("merchants", "kyb_reason")
    op.drop_column("merchants", "kyb_reviewed_at")
    op.drop_column("merchants", "kyb_status")
