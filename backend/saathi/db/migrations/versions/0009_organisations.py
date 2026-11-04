"""the network directory: labs, pharmacies, distributors, cabs, hotels

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-04 14:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0009'
down_revision = '0008'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'organisations',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('name', sa.String(length=160), nullable=False),
        sa.Column('type', sa.String(length=32), nullable=False),
        sa.Column('mode', sa.String(length=16), nullable=False, server_default='simulated'),
        sa.Column('active', sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column('payload_json', sa.Text(), nullable=False),
    )
    op.create_index('ix_organisations_type', 'organisations', ['type'])


def downgrade() -> None:
    op.drop_index('ix_organisations_type', table_name='organisations')
    op.drop_table('organisations')
