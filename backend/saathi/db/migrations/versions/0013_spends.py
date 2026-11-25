"""a family's spends, and what they said they can manage

Revision ID: 0013
Revises: 0012
Create Date: 2026-11-25 00:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0013'
down_revision = '0012'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'spend_entries',
        sa.Column('id', sa.String(length=96), nullable=False),
        sa.Column('patient_id', sa.String(length=32), nullable=False),
        sa.Column('source', sa.String(length=32), nullable=False),
        sa.Column('source_ref', sa.String(length=128), nullable=True),
        sa.Column('payload_json', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('ix_spend_entries_patient_id', 'spend_entries', ['patient_id'])
    op.create_index('ix_spend_entries_source_ref', 'spend_entries', ['source_ref'])
    op.create_table(
        'stated_limits',
        sa.Column('patient_id', sa.String(length=32), nullable=False),
        sa.Column('payload_json', sa.Text(), nullable=False),
        sa.PrimaryKeyConstraint('patient_id'),
    )


def downgrade() -> None:
    op.drop_table('stated_limits')
    op.drop_index('ix_spend_entries_source_ref', table_name='spend_entries')
    op.drop_index('ix_spend_entries_patient_id', table_name='spend_entries')
    op.drop_table('spend_entries')
