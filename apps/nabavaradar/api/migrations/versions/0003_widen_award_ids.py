"""Widen award.lot_id and award.winner_national_id (real notices exceed 32 characters)

Revision ID: 0003
Revises: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0003"
down_revision = "0002"


def upgrade() -> None:
    op.alter_column("award", "lot_id", type_=sa.String(128), existing_nullable=False)
    op.alter_column("award", "winner_national_id", type_=sa.String(128), existing_nullable=True)


def downgrade() -> None:
    op.alter_column("award", "winner_national_id", type_=sa.String(32), existing_nullable=True)
    op.alter_column("award", "lot_id", type_=sa.String(32), existing_nullable=False)
