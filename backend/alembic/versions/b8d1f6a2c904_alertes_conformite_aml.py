"""conformité : file d'alertes AML

Revision ID: b8d1f6a2c904
Revises: a3c7e91d5f28
Create Date: 2026-09-09 15:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "b8d1f6a2c904"
down_revision: str | None = "a3c7e91d5f28"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "compliance_alerts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=16), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="OPEN"),
        sa.Column("score", sa.SmallInteger(), nullable=False, server_default="0"),
        sa.Column(
            "detail", postgresql.JSONB(astext_type=sa.Text()), nullable=False
        ),
        sa.Column("window_key", sa.String(length=80), nullable=False),
        sa.Column("reviewed_by", sa.String(length=80), nullable=True),
        sa.Column("resolution_note", sa.String(length=500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            name=op.f("fk_compliance_alerts_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_compliance_alerts")),
        sa.UniqueConstraint(
            "user_id", "kind", "window_key", name="uq_compliance_alert_window"
        ),
    )
    op.create_index(
        "ix_compliance_alerts_status", "compliance_alerts", ["status"], unique=False
    )
    op.create_index(
        "ix_compliance_alerts_created_at",
        "compliance_alerts",
        ["created_at"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_compliance_alerts_created_at", table_name="compliance_alerts")
    op.drop_index("ix_compliance_alerts_status", table_name="compliance_alerts")
    op.drop_table("compliance_alerts")
