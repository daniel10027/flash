"""agents : hiérarchie master + cumul des commissions

Revision ID: f2a9c1e83b47
Revises: e1f4b7c92a05
Create Date: 2026-09-09 13:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "f2a9c1e83b47"
down_revision: str | None = "e1f4b7c92a05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "agents", sa.Column("parent_agent_id", sa.String(length=36), nullable=True)
    )
    op.add_column(
        "agents",
        sa.Column(
            "commission_earned_minor",
            sa.BigInteger(),
            nullable=False,
            server_default="0",
        ),
    )
    op.add_column(
        "agents",
        sa.Column(
            "commission_paid_minor", sa.BigInteger(), nullable=False, server_default="0"
        ),
    )
    op.create_check_constraint(
        "commission_paid_le_earned",
        "agents",
        "commission_paid_minor <= commission_earned_minor",
    )
    op.create_index(
        "ix_agents_parent_agent_id", "agents", ["parent_agent_id"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_agents_parent_agent_id", table_name="agents")
    op.drop_constraint("commission_paid_le_earned", "agents", type_="check")
    op.drop_column("agents", "commission_paid_minor")
    op.drop_column("agents", "commission_earned_minor")
    op.drop_column("agents", "parent_agent_id")
