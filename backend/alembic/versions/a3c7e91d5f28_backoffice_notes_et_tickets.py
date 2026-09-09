"""back-office : notes de compte + tickets de support

Revision ID: a3c7e91d5f28
Revises: f2a9c1e83b47
Create Date: 2026-09-09 14:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "a3c7e91d5f28"
down_revision: str | None = "f2a9c1e83b47"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "support_notes",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("subject_user_id", sa.String(length=36), nullable=False),
        sa.Column("author", sa.String(length=80), nullable=False),
        sa.Column("body", sa.String(length=2000), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["subject_user_id"],
            ["users.id"],
            name=op.f("fk_support_notes_subject_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_notes")),
    )
    op.create_index(
        "ix_support_notes_subject_user_id", "support_notes", ["subject_user_id"], unique=False
    )

    op.create_table(
        "support_tickets",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("subject_user_id", sa.String(length=36), nullable=False),
        sa.Column("opened_by", sa.String(length=80), nullable=False),
        sa.Column("subject", sa.String(length=160), nullable=False),
        sa.Column("status", sa.String(length=12), nullable=False, server_default="OPEN"),
        sa.Column("last_actor", sa.String(length=80), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["subject_user_id"],
            ["users.id"],
            name=op.f("fk_support_tickets_subject_user_id_users"),
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_support_tickets")),
    )
    op.create_index(
        "ix_support_tickets_subject_user_id",
        "support_tickets",
        ["subject_user_id"],
        unique=False,
    )
    op.create_index(
        "ix_support_tickets_status", "support_tickets", ["status"], unique=False
    )


def downgrade() -> None:
    op.drop_index("ix_support_tickets_status", table_name="support_tickets")
    op.drop_index("ix_support_tickets_subject_user_id", table_name="support_tickets")
    op.drop_table("support_tickets")
    op.drop_index("ix_support_notes_subject_user_id", table_name="support_notes")
    op.drop_table("support_notes")
