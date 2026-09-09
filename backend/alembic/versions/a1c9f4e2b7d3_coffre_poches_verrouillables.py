"""coffre : poches verrouillables

Revision ID: a1c9f4e2b7d3
Revises: 5de023093f5d
Create Date: 2026-09-09 05:10:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = 'a1c9f4e2b7d3'
down_revision: str | None = '5de023093f5d'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'wallets',
        sa.Column(
            'vaulted_minor',
            sa.BigInteger(),
            nullable=False,
            server_default=sa.text('0'),
        ),
    )
    op.alter_column('wallets', 'vaulted_minor', server_default=None)
    op.create_check_constraint(
        op.f('ck_wallets_vaulted_non_negative'), 'wallets', 'vaulted_minor >= 0'
    )

    op.create_table(
        'vault_pockets',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('vault_id', sa.String(length=36), nullable=False),
        sa.Column('wallet_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('name', sa.String(length=60), nullable=False),
        sa.Column('balance_minor', sa.BigInteger(), nullable=False),
        sa.Column('goal_minor', sa.BigInteger(), nullable=True),
        sa.Column('locked_until', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            'balance_minor >= 0',
            name=op.f('ck_vault_pockets_pocket_balance_non_negative'),
        ),
        sa.ForeignKeyConstraint(
            ['wallet_id'],
            ['wallets.id'],
            name=op.f('fk_vault_pockets_wallet_id_wallets'),
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['users.id'],
            name=op.f('fk_vault_pockets_user_id_users'),
            ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_vault_pockets')),
    )
    op.create_index('ix_vault_pockets_wallet_id', 'vault_pockets', ['wallet_id'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_vault_pockets_wallet_id', table_name='vault_pockets')
    op.drop_table('vault_pockets')
    op.drop_constraint(op.f('ck_wallets_vaulted_non_negative'), 'wallets', type_='check')
    op.drop_column('wallets', 'vaulted_minor')
