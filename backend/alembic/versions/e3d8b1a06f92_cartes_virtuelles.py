"""cartes virtuelles

Revision ID: e3d8b1a06f92
Revises: c7f2a0e9d4b1
Create Date: 2026-09-09 06:20:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = 'e3d8b1a06f92'
down_revision: str | None = 'c7f2a0e9d4b1'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'cards',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('wallet_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('network', sa.String(length=12), nullable=False),
        sa.Column('pan_token', sa.String(length=64), nullable=False),
        sa.Column('last4', sa.String(length=4), nullable=False),
        sa.Column('expiry_month', sa.SmallInteger(), nullable=False),
        sa.Column('expiry_year', sa.SmallInteger(), nullable=False),
        sa.Column('status', sa.String(length=8), nullable=False),
        sa.Column('daily_limit_minor', sa.BigInteger(), nullable=False),
        sa.Column('monthly_limit_minor', sa.BigInteger(), nullable=False),
        sa.Column('channels', sa.String(length=64), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint('daily_limit_minor > 0', name=op.f('ck_cards_card_daily_limit_positive')),
        sa.CheckConstraint(
            'monthly_limit_minor > 0', name=op.f('ck_cards_card_monthly_limit_positive')
        ),
        sa.ForeignKeyConstraint(
            ['wallet_id'], ['wallets.id'], name=op.f('fk_cards_wallet_id_wallets'),
            ondelete='RESTRICT',
        ),
        sa.ForeignKeyConstraint(
            ['user_id'], ['users.id'], name=op.f('fk_cards_user_id_users'), ondelete='RESTRICT'
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_cards')),
        sa.UniqueConstraint('pan_token', name=op.f('uq_cards_pan_token')),
    )
    op.create_index('ix_cards_user_id', 'cards', ['user_id'], unique=False)

    op.create_table(
        'card_authorizations',
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('card_id', sa.String(length=36), nullable=False),
        sa.Column('wallet_id', sa.String(length=36), nullable=False),
        sa.Column('user_id', sa.String(length=36), nullable=False),
        sa.Column('authorization_id', sa.String(length=80), nullable=False),
        sa.Column('amount_minor', sa.BigInteger(), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('channel', sa.String(length=12), nullable=False),
        sa.Column('merchant_name', sa.String(length=140), nullable=True),
        sa.Column('status', sa.String(length=12), nullable=False),
        sa.Column('decline_reason', sa.String(length=40), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('captured_minor', sa.BigInteger(), nullable=True),
        sa.Column('ledger_transaction_id', sa.String(length=36), nullable=True),
        sa.CheckConstraint(
            'amount_minor > 0', name=op.f('ck_card_authorizations_card_auth_amount_positive')
        ),
        sa.ForeignKeyConstraint(
            ['card_id'], ['cards.id'], name=op.f('fk_card_authorizations_card_id_cards'),
            ondelete='RESTRICT',
        ),
        sa.PrimaryKeyConstraint('id', name=op.f('pk_card_authorizations')),
        sa.UniqueConstraint(
            'authorization_id', name=op.f('uq_card_authorizations_authorization_id')
        ),
    )
    op.create_index(
        'ix_card_authorizations_card_recent',
        'card_authorizations',
        ['card_id', 'created_at'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index('ix_card_authorizations_card_recent', table_name='card_authorizations')
    op.drop_table('card_authorizations')
    op.drop_index('ix_cards_user_id', table_name='cards')
    op.drop_table('cards')
