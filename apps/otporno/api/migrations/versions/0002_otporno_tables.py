"""Otporko tables: municipality, cell, flood_zone, flood_cell, heat_point, heat_cell, candidate_site,
action_rule, precompute_status, api_call_log

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
    # opendata_core.popgrid.PopGridCell (the same definition as in the blizu migration)
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
        "municipality",
        sa.Column("lau_id", sa.String(16), primary_key=True),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("geom", Geometry("MULTIPOLYGON", srid=4326, spatial_index=False), nullable=False),
        sa.Column("area_km2", sa.Float),
        sa.Column("attrs", JSON, nullable=False, server_default="{}"),
    )
    op.create_index("ix_municipality_name", "municipality", ["name"])
    _gist("municipality")

    op.create_table(
        "cell",
        sa.Column("grd_id", sa.String(48), primary_key=True),
        sa.Column("geom", Geometry("POLYGON", srid=4326, spatial_index=False), nullable=False),
        sa.Column("centroid", Geometry("POINT", srid=4326, spatial_index=False), nullable=False),
        sa.Column("pop_total", sa.Integer),
        sa.Column("pop_65p", sa.Integer),
        sa.Column("lau_id", sa.String(16), sa.ForeignKey("municipality.lau_id")),
    )
    op.create_index("ix_cell_lau_id", "cell", ["lau_id"])
    _gist("cell")
    _gist("cell", "centroid")

    op.create_table(
        "flood_zone",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("scenario", sa.String(8), nullable=False),
        sa.Column("geom", Geometry("MULTIPOLYGON", srid=3765, spatial_index=False), nullable=False),
    )
    op.create_index("ix_flood_zone_scenario", "flood_zone", ["scenario"])
    _gist("flood_zone")

    op.create_table(
        "flood_cell",
        sa.Column("grd_id", sa.String(48), sa.ForeignKey("cell.grd_id"), primary_key=True),
        sa.Column("level", sa.SmallInteger, nullable=False),
        sa.Column("share_high", sa.Float),
        sa.Column("share_medium", sa.Float),
        sa.Column("share_low", sa.Float),
        sa.Column("method", sa.String(32), nullable=False),
    )

    op.create_table(
        "heat_point",
        sa.Column("lat_r", sa.Numeric(6, 3), primary_key=True),
        sa.Column("lon_r", sa.Numeric(6, 3), primary_key=True),
        sa.Column("model", sa.String(32), primary_key=True),
        sa.Column("base_hot_days", sa.Float),
        sa.Column("fut_hot_days", sa.Float),
        sa.Column("base_trop_nights", sa.Float),
        sa.Column("fut_trop_nights", sa.Float),
        sa.Column("kind", sa.String(8), nullable=False, server_default="address"),
        sa.Column(
            "fetched_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )

    op.create_table(
        "heat_cell",
        sa.Column("grd_id", sa.String(48), sa.ForeignKey("cell.grd_id"), primary_key=True),
        sa.Column("base_mean", sa.Float, nullable=False),
        sa.Column("fut_mean", sa.Float, nullable=False),
        sa.Column("fut_min", sa.Float, nullable=False),
        sa.Column("fut_max", sa.Float, nullable=False),
        sa.Column("base_trop", sa.Float),
        sa.Column("fut_trop", sa.Float),
        sa.Column("percentile", sa.Float, nullable=False),
        sa.Column("lat_r", sa.Numeric(6, 3), nullable=False),
        sa.Column("lon_r", sa.Numeric(6, 3), nullable=False),
    )

    op.create_table(
        "candidate_site",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("lau_id", sa.String(16), sa.ForeignKey("municipality.lau_id"), nullable=False),
        sa.Column("name", sa.Text),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("geom", Geometry("POINT", srid=4326, spatial_index=False), nullable=False),
        sa.Column("source_id", sa.String(64), sa.ForeignKey("data_source.id"), nullable=False),
        sa.Column("osm_id", sa.String(24)),
    )
    op.create_index("ix_candidate_site_lau_id", "candidate_site", ["lau_id"])
    _gist("candidate_site")

    op.create_table(
        "action_rule",
        sa.Column("id", sa.String(48), primary_key=True),
        sa.Column("hazard", sa.String(12), nullable=False),
        sa.Column("band", sa.String(16), nullable=False),
        sa.Column("audience", sa.String(12), nullable=False),
        sa.Column("text_hr", sa.Text, nullable=False),
        sa.Column("source_title", sa.Text, nullable=False),
        sa.Column("source_url", sa.Text, nullable=False),
    )
    op.create_index("ix_action_rule_hazard", "action_rule", ["hazard"])

    op.create_table(
        "precompute_status",
        sa.Column("lau_id", sa.String(16), sa.ForeignKey("municipality.lau_id"), primary_key=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("message", sa.Text),
        sa.Column("details", JSON, nullable=False, server_default="{}"),
    )

    op.create_table(
        "api_call_log",
        sa.Column("id", sa.BigInteger, primary_key=True, autoincrement=True),
        sa.Column(
            "called_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
        sa.Column("service", sa.String(32), nullable=False),
        sa.Column("cost", sa.Float, nullable=False),
        sa.Column("status", sa.SmallInteger, nullable=False),
        sa.Column("detail", sa.Text),
    )
    op.create_index("ix_api_call_log_called_at", "api_call_log", ["called_at"])


def downgrade() -> None:
    for table in (
        "api_call_log",
        "precompute_status",
        "action_rule",
        "candidate_site",
        "heat_cell",
        "heat_point",
        "flood_cell",
        "flood_zone",
        "cell",
        "municipality",
        "popgrid_cell",
    ):
        op.drop_table(table)
