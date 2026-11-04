"""what each family was told, kept across restarts

Revision ID: 0011
Revises: 0010
Create Date: 2026-11-04 17:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0011'
down_revision = '0010'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'family_messages',
        sa.Column('id', sa.String(length=96), primary_key=True),
        sa.Column('patient_id', sa.String(length=32), nullable=False),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('payload_json', sa.Text(), nullable=False),
    )
    op.create_index('ix_family_messages_patient_id', 'family_messages', ['patient_id'])


def downgrade() -> None:
    op.drop_index('ix_family_messages_patient_id', table_name='family_messages')
    op.drop_table('family_messages')
