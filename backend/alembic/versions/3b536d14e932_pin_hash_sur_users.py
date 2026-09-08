"""pin hash sur users

Revision ID: 3b536d14e932
Revises: d9a7993720f0
Create Date: 2026-09-08 19:39:31.488506
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = '3b536d14e932'
down_revision: str | None = 'd9a7993720f0'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Ajout en deux temps pour rester applicable même si la table contient déjà des lignes.
    op.add_column(
        "users",
        sa.Column("pin_hash", sa.String(length=255), nullable=False, server_default=""),
    )
    op.alter_column("users", "pin_hash", server_default=None)


def downgrade() -> None:
    op.drop_column("users", "pin_hash")
