"""Blizu tables: popgrid_cell, facility, gtfs_stop_frequency, cell, cell_access

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op
from geoalchemy2 import Geometry
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _gist(table: str, column: str = "geom") -> None:
    op.create_index(f"idx_{table}_{column}", table, [column], postgresql_using="gist")


def upgrade() -> None:
    op.create_table(
        "popgrid_cell",
        sa.Column("grd_id", sa.String(48), primary_key=True),
        sa.Column("geom", Geometry("POLYGON", srid=3035, spatial_index=False), nullable=False),
        sa.Column("centroid", Geometry("POINT", srid=4326, spatial_index=False), nullable=False),
        sa.Column("pop_total", sa.BigInteger),
        sa.Column("pop_under15", sa.Integer),
        sa.Column("pop_15_64", sa.Integer),
        sa.Column("pop_65plus", sa.Integer),
        sa.Column("land_surface", sa.Float),
        sa.Column("populated", sa.Boolean, nullable=False),
        sa.Column("cntr_id", sa.String(32), nullable=False),
    )
    _gist("popgrid_cell")
    _gist("popgrid_cell", "centroid")

    op.create_table(
        "facility",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("category", sa.String(16), nullable=False),
        sa.Column("name", sa.Text),
        sa.Column("address", sa.Text),
        sa.Column("geom", Geometry("POINT", srid=4326, spatial_index=False), nullable=False),
        sa.Column("source_id", sa.String(64), sa.ForeignKey("data_source.id"), nullable=False),
        sa.Column("tier", sa.String(16), nullable=False),
        sa.Column("source_record_id", sa.Text),
        sa.Column("attrs", JSON),
        sa.Column(
            "loaded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_facility_category", "facility", ["category"])
    _gist("facility")

    op.create_table(
        "gtfs_stop_frequency",
        sa.Column("stop_id", sa.String(64), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("geom", Geometry("POINT", srid=4326, spatial_index=False), nullable=False),
        sa.Column("dep_per_hour", sa.Float, nullable=False),
        sa.Column("ref_date", sa.String(10), nullable=False),
        sa.Column("feed_date", sa.String(10), nullable=False),
    )
    _gist("gtfs_stop_frequency")

    op.create_table(
        "cell",
        sa.Column("grd_id", sa.String(48), primary_key=True),
        sa.Column("geom", Geometry("POLYGON", srid=4326, spatial_index=False), nullable=False),
        sa.Column("pop_total", sa.Integer),
        sa.Column("pop_u15", sa.Integer),
        sa.Column("pop_65p", sa.Integer),
    )
    _gist("cell")

    op.create_table(
        "cell_access",
        sa.Column("grd_id", sa.String(48), sa.ForeignKey("cell.grd_id"), primary_key=True),
        sa.Column("persona", sa.String(16), primary_key=True),
        sa.Column("category", sa.String(16), primary_key=True),
        sa.Column("mean_minutes", sa.Float, nullable=False),
    )


def downgrade() -> None:
    for table in ("cell_access", "cell", "gtfs_stop_frequency", "facility", "popgrid_cell"):
        op.drop_table(table)
