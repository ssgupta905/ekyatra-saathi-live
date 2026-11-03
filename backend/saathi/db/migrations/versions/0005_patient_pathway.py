"""patients carry their care pathway

Revision ID: 0005
Revises: 0004
Create Date: 2026-11-03 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0005'
down_revision = '0004'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Every patient recorded so far is on the oncology pathway, which is what
    # the server default says.
    with op.batch_alter_table('patients', schema=None) as batch_op:
        batch_op.add_column(
            sa.Column('pathway_id', sa.String(length=32), nullable=False, server_default='oncology')
        )


def downgrade() -> None:
    with op.batch_alter_table('patients', schema=None) as batch_op:
        batch_op.drop_column('pathway_id')
