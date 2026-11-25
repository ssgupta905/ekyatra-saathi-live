"""healthcare places near a family, held locally instead of asked for every time

Revision ID: 0015
Revises: 0014
Create Date: 2026-11-25 00:00:00.000000

The live Overpass servers answer in thirty to forty seconds when they answer at
all, and a family opening "Near you" cannot wait for that. The data itself
barely moves — a pharmacy does not relocate weekly — so it is loaded here
monthly from OpenStreetMap's India extract and queried locally.

Only healthcare points are kept: pharmacies, labs, clinics, physios and
medical suppliers. The whole India extract is 1.7 GB and almost none of it is
about health; filtered, this is roughly a hundred megabytes.

**No rating column, and there will not be one.** Nothing in this system ranks
a clinic by what strangers thought of it, and a column that existed would
eventually be filled. The ordering a family sees is distance and opening
hours, computed in `orchestrator/nearby_needs.py`, with the reasons shown.
"""
from alembic import op
import sqlalchemy as sa


revision = '0015'
down_revision = '0014'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'places',
        # OpenStreetMap's own id, prefixed by element type — "node/123456789".
        # Theirs rather than ours so a monthly reload updates a row instead of
        # duplicating it, and so a place can be looked up on osm.org by hand.
        sa.Column('id', sa.String(length=40), primary_key=True),
        sa.Column('kind', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=200), nullable=False, server_default=''),
        sa.Column('address', sa.String(length=300), nullable=False, server_default=''),
        sa.Column('latitude', sa.Float(), nullable=False),
        sa.Column('longitude', sa.Float(), nullable=False),
        sa.Column('phone', sa.String(length=40), nullable=True),
        # OpenStreetMap's `opening_hours` string, kept raw. Parsing it is the
        # adapter's job and the parser already exists for the live reader —
        # storing a parsed form would mean two parsers to keep in agreement.
        sa.Column('opening_hours', sa.String(length=300), nullable=True),
        sa.Column('loaded_at', sa.DateTime(timezone=True), nullable=False),
    )
    # Every query is "this kind, inside this box". Kind first because it cuts
    # hardest: pharmacies outnumber physios by a wide margin.
    op.create_index('ix_places_kind_lat_lon', 'places', ['kind', 'latitude', 'longitude'])


def downgrade() -> None:
    op.drop_index('ix_places_kind_lat_lon', table_name='places')
    op.drop_table('places')
