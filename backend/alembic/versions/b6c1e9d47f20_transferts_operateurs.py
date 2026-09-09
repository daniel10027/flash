"""transferts opérateurs (interop payout / collect)

Revision ID: b6c1e9d47f20
Revises: a8e3d5f10c47
Create Date: 2026-09-09 08:05:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = 'b6c1e9d47f20'
down_revision: str | None = 'a8e3d5f10c47'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'operator_transfers',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('wallet_id', sa.String(length=36), nullable=False),
        sa.Column('operator', sa.String(length=32), nullable=False),
        sa.Column('direction', sa.String(length=8), nullable=False),
        sa.Column('msisdn', sa.String(length=20), nullable=False),
        sa.Column('amount_minor', sa.BigInteger(), nullable=False),
        sa.Column('fee_minor', sa.BigInteger(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('reference', sa.String(length=64), nullable=False),
        sa.Column('external_ref', sa.String(length=64), nullable=True),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('failure_reason', sa.String(length=120), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ledger_transaction_id', sa.String(length=36), nullable=True),
        sa.CheckConstraint(
            'amount_minor > 0',
            name=op.f('ck_operator_transfers_operator_transfer_amount_positive'),
        ),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['users.id'],
            name=op.f('fk_operator_transfers_user_id_users'),
            ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_operator_transfers')),
        sa.UniqueConstraint('reference', name=op.f('uq_operator_transfers_reference')),
    )
    op.create_index(
        'ix_operator_transfers_user_id', 'operator_transfers', ['user_id'], unique=False
    )


def downgrade() -> None:
    op.drop_index('ix_operator_transfers_user_id', table_name='operator_transfers')
    op.drop_table('operator_transfers')
