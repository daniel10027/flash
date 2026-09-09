"""plans d'épargne

Revision ID: c7f2a0e9d4b1
Revises: a1c9f4e2b7d3
Create Date: 2026-09-09 05:45:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = 'c7f2a0e9d4b1'
down_revision: str | None = 'a1c9f4e2b7d3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        'wallets',
        sa.Column('saved_minor', sa.BigInteger(), nullable=False, server_default=sa.text('0')),
    )
    op.alter_column('wallets', 'saved_minor', server_default=None)
    op.create_check_constraint(
        op.f('ck_wallets_saved_non_negative'), 'wallets', 'saved_minor >= 0'
    )

    op.create_table(
        'savings_plans',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('wallet_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('name', sa.String(length=60), nullable=False),
        sa.Column('balance_minor', sa.BigInteger(), nullable=False),
        sa.Column('annual_rate_bps', sa.SmallInteger(), nullable=False),
        sa.Column('frequency', sa.String(length=8), nullable=False),
        sa.Column('contribution_minor', sa.BigInteger(), nullable=False),
        sa.Column('target_minor', sa.BigInteger(), nullable=True),
        sa.Column('target_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('next_contribution_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('last_accrual_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('accrued_micro', sa.BigInteger(), nullable=False),
        sa.Column('status', sa.String(length=8), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            'balance_minor >= 0', name=op.f('ck_savings_plans_plan_balance_non_negative')
        ),
        sa.CheckConstraint(
            'accrued_micro >= 0', name=op.f('ck_savings_plans_plan_accrued_non_negative')
        ),
        sa.ForeignKeyConstraint(
            ['wallet_id'],
            ['wallets.id'],
            name=op.f('fk_savings_plans_wallet_id_wallets'),
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['user_id'],
            ['users.id'],
            name=op.f('fk_savings_plans_user_id_users'),
            ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_savings_plans')),
    )
    op.create_index('ix_savings_plans_user_id', 'savings_plans', ['user_id'], unique=False)
    op.create_index(
        'ix_savings_plans_due',
        'savings_plans',
        ['next_contribution_at'],
        unique=False,
        postgresql_where=sa.text("status = 'ACTIVE' AND next_contribution_at IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index(
        'ix_savings_plans_due',
        table_name='savings_plans',
        postgresql_where=sa.text("status = 'ACTIVE' AND next_contribution_at IS NOT NULL"),
    )
    op.drop_index('ix_savings_plans_user_id', table_name='savings_plans')
    op.drop_table('savings_plans')
    op.drop_constraint(op.f('ck_wallets_saved_non_negative'), 'wallets', type_='check')
    op.drop_column('wallets', 'saved_minor')
