"""patients can be reached, and sign in, by email

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-04 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0008'
down_revision = '0007'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('patients', schema=None) as batch_op:
        batch_op.add_column(sa.Column('caregiver_email', sa.String(length=254), nullable=True))
        batch_op.create_index('ix_patients_caregiver_email', ['caregiver_email'])


def downgrade() -> None:
    with op.batch_alter_table('patients', schema=None) as batch_op:
        batch_op.drop_index('ix_patients_caregiver_email')
        batch_op.drop_column('caregiver_email')
