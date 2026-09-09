"""registre d'audit chaîné

Revision ID: a8e3d5f10c47
Revises: f4b7c2109ea3
Create Date: 2026-09-09 07:35:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'a8e3d5f10c47'
down_revision: str | None = 'f4b7c2109ea3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'audit_entries',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('sequence', sa.BigInteger(), nullable=False),
        sa.Column('actor', sa.String(length=64), nullable=False),
        sa.Column('role', sa.String(length=24), nullable=False),
        sa.Column('action', sa.String(length=48), nullable=False),
        sa.Column('resource_type', sa.String(length=48), nullable=False),
        sa.Column('resource_id', sa.String(length=64), nullable=False),
        sa.Column('before', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('after', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('occurred_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('prev_hash', sa.String(length=64), nullable=False),
        sa.Column('entry_hash', sa.String(length=64), nullable=False),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_audit_entries')),
        sa.UniqueConstraint('sequence', name=op.f('uq_audit_entries_sequence')),
        sa.UniqueConstraint('entry_hash', name=op.f('uq_audit_entries_entry_hash')),
    )
    op.create_index('ix_audit_entries_sequence', 'audit_entries', ['sequence'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_audit_entries_sequence', table_name='audit_entries')
    op.drop_table('audit_entries')
