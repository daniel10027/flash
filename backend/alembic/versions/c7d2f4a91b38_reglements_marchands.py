"""règlements marchands (settlement config + virements bancaires)

Revision ID: c7d2f4a91b38
Revises: b6c1e9d47f20
Create Date: 2026-09-09 09:30:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c7d2f4a91b38'
down_revision: str | None = 'b6c1e9d47f20'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'merchant_settlements',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('merchant_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('amount_minor', sa.BigInteger(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('payment_count', sa.BigInteger(), nullable=False),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('bank_reference', sa.String(length=64), nullable=True),
        sa.Column('failure_reason', sa.String(length=160), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('settled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('ledger_transaction_id', sa.String(length=36), nullable=True),
        sa.CheckConstraint(
            'amount_minor > 0',
            name=op.f('ck_merchant_settlements_merchant_settlement_amount_positive'),
        ),
        sa.ForeignKeyConstraint(
            ['merchant_id'],
            ['merchants.id'],
            name=op.f('fk_merchant_settlements_merchant_id_merchants'),
            ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_merchant_settlements')),
    )
    op.create_index(
        'ix_merchant_settlements_merchant_id',
        'merchant_settlements',
        ['merchant_id'],
        unique=False,
    )

    op.add_column(
        'merchants',
        sa.Column(
            'settlement_frequency',
            sa.String(length=8),
            nullable=False,
            server_default='MANUAL',
        ),
    )
    op.add_column('merchants', sa.Column('bank_holder', sa.String(length=120), nullable=True))
    op.add_column('merchants', sa.Column('bank_iban', sa.String(length=40), nullable=True))
    op.add_column('merchants', sa.Column('bank_name', sa.String(length=120), nullable=True))
    op.add_column(
        'merchants',
        sa.Column('next_settlement_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        'merchants', sa.Column('last_settlement_id', sa.String(length=36), nullable=True)
    )
    op.create_index(
        'ix_merchants_settlement_due',
        'merchants',
        ['next_settlement_at'],
        unique=False,
        postgresql_where=sa.text(
            "status = 'ACTIVE' AND next_settlement_at IS NOT NULL "
            "AND bank_iban IS NOT NULL"
        ),
    )

    op.add_column(
        'merchant_payments',
        sa.Column('settlement_id', sa.String(length=36), nullable=True),
    )
    op.create_index(
        'ix_merchant_payments_settlement_id',
        'merchant_payments',
        ['settlement_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_merchant_payments_settlement_id', table_name='merchant_payments')
    op.drop_column('merchant_payments', 'settlement_id')

    op.drop_index('ix_merchants_settlement_due', table_name='merchants')
    op.drop_column('merchants', 'last_settlement_id')
    op.drop_column('merchants', 'next_settlement_at')
    op.drop_column('merchants', 'bank_name')
    op.drop_column('merchants', 'bank_iban')
    op.drop_column('merchants', 'bank_holder')
    op.drop_column('merchants', 'settlement_frequency')

    op.drop_index(
        'ix_merchant_settlements_merchant_id', table_name='merchant_settlements'
    )
    op.drop_table('merchant_settlements')
