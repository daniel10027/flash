"""référentiel pays / opérateurs

Revision ID: f4b7c2109ea3
Revises: e3d8b1a06f92
Create Date: 2026-09-09 07:05:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = 'f4b7c2109ea3'
down_revision: str | None = 'e3d8b1a06f92'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        'countries',
        sa.Column('code', sa.String(length=2), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('currency', sa.String(length=3), nullable=False),
        sa.Column('dialing_code', sa.String(length=6), nullable=False),
        sa.Column('timezone', sa.String(length=48), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.PrimaryKeyConstraint('code', name=op.f('pk_countries')),
    )
    op.create_table(
        'operators',
        sa.Column('code', sa.String(length=32), nullable=False),
        sa.Column('country_code', sa.String(length=2), nullable=False),
        sa.Column('name', sa.String(length=80), nullable=False),
        sa.Column('msisdn_prefixes', sa.String(length=200), nullable=False),
        sa.Column('active', sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(
            ['country_code'],
            ['countries.code'],
            name=op.f('fk_operators_country_code_countries'),
            ondelete='CASCADE',
        ),
        sa.PrimaryKeyConstraint('code', name=op.f('pk_operators')),
    )
    op.create_index('ix_operators_country_code', 'operators', ['country_code'], unique=False)


def downgrade() -> None:
    op.drop_index('ix_operators_country_code', table_name='operators')
    op.drop_table('operators')
    op.drop_table('countries')
