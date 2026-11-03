"""Reusable Alembic operations for the ``opendata_core`` tables.

Usage in an app migration (``apps/<app>/api/migrations/versions/0001_core.py``)::

    from opendata_core.alembic_template.provenance_migration import downgrade, upgrade

    revision = "0001"
    down_revision = None

``upgrade()`` creates ``data_source``, ``ingestion_run`` and ``geocode_cache``;
``downgrade()`` drops them. Keep column definitions in sync with ``provenance.py`` /
``geocode.py`` (a test compares migration output with the ORM metadata).
"""

from __future__ import annotations

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

_ACCESS = ("api", "download", "wms", "derived")
_TIER = ("official", "eu_official", "community", "derived")
_STATUS = ("ok", "partial", "failed")


def _enum(name: str, values: tuple[str, ...]) -> sa.Enum:
    return sa.Enum(*values, name=name, native_enum=False, length=16)


def upgrade() -> None:
    """Create provenance and geocode-cache tables."""
    op.create_table(
        "data_source",
        sa.Column("id", sa.String(64), primary_key=True),
        sa.Column("title", sa.Text, nullable=False),
        sa.Column("publisher", sa.Text, nullable=False),
        sa.Column("url", sa.Text, nullable=False),
        sa.Column("license_name", sa.Text),
        sa.Column("license_url", sa.Text),
        sa.Column("access_method", _enum("access_method", _ACCESS), nullable=False),
        sa.Column("tier", _enum("source_tier", _TIER), nullable=False),
        sa.Column("notes", sa.Text),
    )
    op.create_table(
        "ingestion_run",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source_id", sa.String(64), sa.ForeignKey("data_source.id"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True)),
        sa.Column("status", _enum("run_status", _STATUS), nullable=False),
        sa.Column("rows", sa.Integer),
        sa.Column("sha256", sa.String(64)),
        sa.Column("source_last_modified", sa.DateTime(timezone=True)),
        sa.Column("retrieved_url", sa.Text),
        sa.Column("error", sa.Text),
    )
    op.create_index("ix_ingestion_run_source_id", "ingestion_run", ["source_id"])
    op.create_table(
        "geocode_cache",
        sa.Column("q_norm", sa.Text, primary_key=True),
        sa.Column(
            "response", sa.JSON().with_variant(postgresql.JSONB(), "postgresql"), nullable=False
        ),
        sa.Column("fetched_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    """Drop provenance and geocode-cache tables."""
    op.drop_table("geocode_cache")
    op.drop_index("ix_ingestion_run_source_id", table_name="ingestion_run")
    op.drop_table("ingestion_run")
    op.drop_table("data_source")
