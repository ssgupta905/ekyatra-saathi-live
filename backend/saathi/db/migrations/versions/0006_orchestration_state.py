"""orchestration state survives a restart

Revision ID: 0006
Revises: 0005
Create Date: 2026-11-03 11:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0006'
down_revision = '0005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table('disruptions',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('resource_id', sa.String(length=64), nullable=False),
    sa.Column('unavailable_to', sa.Date(), nullable=True),
    sa.Column('payload_json', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('disruptions', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_disruptions_resource_id'), ['resource_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_disruptions_unavailable_to'), ['unavailable_to'], unique=False)

    op.create_table('readiness_items',
    sa.Column('patient_id', sa.String(length=32), nullable=False),
    sa.Column('item_id', sa.String(length=96), nullable=False),
    sa.Column('payload_json', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('patient_id', 'item_id')
    )

    op.create_table('option_sets',
    sa.Column('patient_id', sa.String(length=32), nullable=False),
    sa.Column('disruption_id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('payload_json', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('patient_id')
    )
    with op.batch_alter_table('option_sets', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_option_sets_disruption_id'), ['disruption_id'], unique=False)

    op.create_table('approvals',
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('patient_id', sa.String(length=32), nullable=False),
    sa.Column('disruption_id', sa.String(length=36), nullable=False),
    sa.Column('approved_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('payload_json', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('approvals', schema=None) as batch_op:
        batch_op.create_index(batch_op.f('ix_approvals_patient_id'), ['patient_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_approvals_disruption_id'), ['disruption_id'], unique=False)
        batch_op.create_index(batch_op.f('ix_approvals_approved_at'), ['approved_at'], unique=False)


def downgrade() -> None:
    op.drop_table('approvals')
    op.drop_table('option_sets')
    op.drop_table('readiness_items')
    op.drop_table('disruptions')
