"""grilles tarifaires & plafonds éditables

Revision ID: c3f5a9e0d182
Revises: b8d1f6a2c904
Create Date: 2026-09-09 16:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "c3f5a9e0d182"
down_revision: str | None = "b8d1f6a2c904"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "pricing_rules",
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("percent_bps", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column("fixed_fee_minor", sa.BigInteger(), nullable=True),
        sa.Column("min_fee_minor", sa.BigInteger(), nullable=True),
        sa.Column("max_fee_minor", sa.BigInteger(), nullable=True),
        sa.Column("rounding", sa.String(length=16), nullable=False, server_default="HALF_UP"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "percent_bps between 0 and 10000",
            name=op.f("ck_pricing_rules_percent_bps_range"),
        ),
        sa.PrimaryKeyConstraint(
            "country_code", "operation", name=op.f("pk_pricing_rules")
        ),
    )
    op.create_table(
        "limit_rules",
        sa.Column("country_code", sa.String(length=2), nullable=False),
        sa.Column("kyc_tier", sa.SmallInteger(), nullable=False),
        sa.Column("operation", sa.String(length=32), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("per_tx_minor", sa.BigInteger(), nullable=True),
        sa.Column("daily_minor", sa.BigInteger(), nullable=True),
        sa.Column("monthly_minor", sa.BigInteger(), nullable=True),
        sa.Column("balance_max_minor", sa.BigInteger(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kyc_tier between 0 and 2", name=op.f("ck_limit_rules_kyc_tier_range")
        ),
        sa.PrimaryKeyConstraint(
            "country_code", "kyc_tier", "operation", name=op.f("pk_limit_rules")
        ),
    )


def downgrade() -> None:
    op.drop_table("limit_rules")
    op.drop_table("pricing_rules")
