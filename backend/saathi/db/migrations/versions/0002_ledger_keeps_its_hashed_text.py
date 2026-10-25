"""ledger keeps its hashed text

Revision ID: 0002
Revises: 0001
Create Date: 2026-10-25 18:18:31.737295
"""
from alembic import op
import sqlalchemy as sa


revision = '0002'
down_revision = '0001'
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table('evidence_ledger', schema=None) as batch_op:
        batch_op.add_column(sa.Column('recorded_at_iso', sa.String(length=40), nullable=False, server_default=''))
        batch_op.add_column(sa.Column('metadata_json', sa.Text(), nullable=False, server_default='{}'))


def downgrade() -> None:
    with op.batch_alter_table('evidence_ledger', schema=None) as batch_op:
        batch_op.drop_column('metadata_json')
        batch_op.drop_column('recorded_at_iso')
