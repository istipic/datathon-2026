"""vrtic_free_places

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0003"
down_revision = "0002"

JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def upgrade() -> None:
    op.create_table(
        "vrtic_free_places",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("snapshot_date", sa.String(10)),
        sa.Column("district", sa.Text, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("branches", sa.Text),
        sa.Column("jaslice_free", sa.Integer, nullable=False),
        sa.Column("vrtic_free", sa.Integer, nullable=False),
        sa.Column("total_free", sa.Integer, nullable=False),
        sa.Column("resource_name", sa.Text),
        sa.Column("attrs", JSON),
    )


def downgrade() -> None:
    op.drop_table("vrtic_free_places")
