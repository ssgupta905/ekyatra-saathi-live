"""onboarding: a family's profile, documents and admissions

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-04 15:00:00.000000
"""
from alembic import op
import sqlalchemy as sa


revision = '0010'
down_revision = '0009'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'family_profiles',
        sa.Column('patient_id', sa.String(length=32), primary_key=True),
        sa.Column('sections_json', sa.Text(), nullable=False, server_default='{}'),
        sa.Column('activated_by', sa.String(length=160), nullable=True),
        sa.Column('activated_at', sa.DateTime(timezone=True), nullable=True),
    )
    op.create_table(
        'profile_documents',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('patient_id', sa.String(length=32), nullable=False),
        sa.Column('meta_json', sa.Text(), nullable=False),
        sa.Column('content', sa.LargeBinary(), nullable=False),
    )
    op.create_index('ix_profile_documents_patient_id', 'profile_documents', ['patient_id'])
    op.create_table(
        'admissions',
        sa.Column('id', sa.String(length=64), primary_key=True),
        sa.Column('patient_id', sa.String(length=32), nullable=False),
        sa.Column('payload_json', sa.Text(), nullable=False),
    )
    op.create_index('ix_admissions_patient_id', 'admissions', ['patient_id'])


def downgrade() -> None:
    op.drop_index('ix_admissions_patient_id', table_name='admissions')
    op.drop_table('admissions')
    op.drop_index('ix_profile_documents_patient_id', table_name='profile_documents')
    op.drop_table('profile_documents')
    op.drop_table('family_profiles')
