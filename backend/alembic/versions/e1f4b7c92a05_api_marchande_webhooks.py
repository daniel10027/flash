"""API marchande publique : webhooks marchand signés

Revision ID: e1f4b7c92a05
Revises: d4e8a1c6b923
Create Date: 2026-09-09 12:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e1f4b7c92a05"
down_revision: str | None = "d4e8a1c6b923"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("merchants", sa.Column("webhook_url", sa.String(length=300), nullable=True))
    op.add_column(
        "merchants", sa.Column("webhook_secret", sa.String(length=128), nullable=True)
    )

    op.create_table(
        "merchant_webhook_deliveries",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("merchant_id", sa.String(length=36), nullable=False),
        sa.Column("source_id", sa.String(length=36), nullable=False),
        sa.Column("event_type", sa.String(length=40), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="PENDING"),
        sa.Column("attempts", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.String(length=200), nullable=True),
        sa.ForeignKeyConstraint(
            ["merchant_id"],
            ["merchants.id"],
            name=op.f("fk_merchant_webhook_deliveries_merchant_id_merchants"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_merchant_webhook_deliveries")),
        sa.UniqueConstraint(
            "event_type", "source_id", name="uq_merchant_webhook_source"
        ),
    )
    op.create_index(
        "ix_merchant_webhook_deliveries_due",
        "merchant_webhook_deliveries",
        ["next_attempt_at"],
        unique=False,
        postgresql_where=sa.text("status = 'PENDING'"),
    )


def downgrade() -> None:
    op.drop_index(
        "ix_merchant_webhook_deliveries_due", table_name="merchant_webhook_deliveries"
    )
    op.drop_table("merchant_webhook_deliveries")
    op.drop_column("merchants", "webhook_secret")
    op.drop_column("merchants", "webhook_url")
