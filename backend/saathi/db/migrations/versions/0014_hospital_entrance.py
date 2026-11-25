"""where a hospital's entrance is, so a family's ride app can be opened at it

Revision ID: 0014
Revises: 0013
Create Date: 2026-11-25 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0014'
down_revision = '0013'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Null for every hospital that has not been given one, which is the safe way
    # for it to be missing: the ride and stay apps then open without a destination.
    op.add_column('hospitals', sa.Column('latitude', sa.Float(), nullable=True))
    op.add_column('hospitals', sa.Column('longitude', sa.Float(), nullable=True))
    op.add_column('hospitals', sa.Column('address', sa.String(length=200), nullable=True))


def downgrade() -> None:
    op.drop_column('hospitals', 'address')
    op.drop_column('hospitals', 'longitude')
    op.drop_column('hospitals', 'latitude')
