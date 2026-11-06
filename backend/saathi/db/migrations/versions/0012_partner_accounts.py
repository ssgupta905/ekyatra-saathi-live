"""a vendor account answers for one organisation

Revision ID: 0012
Revises: 0011
Create Date: 2026-11-06 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0012'
down_revision = '0011'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Which organisation this account speaks for. Null for every staff account,
    # which is most of them; a partner account without one can see nothing,
    # which is the safe way for the binding to be missing.
    op.add_column('users', sa.Column('organisation_id', sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'organisation_id')
