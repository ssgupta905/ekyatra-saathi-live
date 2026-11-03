"""consent survives a restart

Revision ID: 0007
Revises: 0006
Create Date: 2026-11-03 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0007'
down_revision = '0006'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('consent_requests',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('abha_number', sa.String(length=32), nullable=False),
    sa.Column('payload_json', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('consent_requests', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_consent_requests_abha_number'), ['abha_number'], unique=False)

    op.create_table('consent_grants',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('abha_number', sa.String(length=32), nullable=False),
    sa.Column('payload_json', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('consent_grants', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_consent_grants_abha_number'), ['abha_number'], unique=False)

    op.create_table('record_pointers',
    sa.Column('id', sa.String(length=64), nullable=False),
    sa.Column('abha_number', sa.String(length=32), nullable=False),
    sa.Column('payload_json', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('record_pointers', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_record_pointers_abha_number'), ['abha_number'], unique=False)

    op.create_table('access_attempts',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('abha_number', sa.String(length=32), nullable=False),
    sa.Column('at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('payload_json', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('access_attempts', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_access_attempts_abha_number'), ['abha_number'], unique=False)
        batch_op.create_index(batch_op.f('ix_access_attempts_at'), ['at'], unique=False)


def downgrade() -> None:
    op.drop_table('access_attempts')
    op.drop_table('record_pointers')
    op.drop_table('consent_grants')
    op.drop_table('consent_requests')
