"""Threshold e-mail alerts: subscription preferences, sent-notice log and exclusions

Revision ID: 0004
Revises: 0003
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision = "0004"
down_revision = "0003"


def upgrade() -> None:
    op.add_column(
        "subscription", sa.Column("min_fit", sa.Float(), nullable=False, server_default="0.75")
    )
    op.add_column("subscription", sa.Column("min_value_eur", sa.Numeric(16, 2), nullable=True))
    op.add_column(
        "subscription",
        sa.Column("counties", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "subscription",
        sa.Column("cpv_divisions", postgresql.JSONB(), nullable=False, server_default="[]"),
    )
    op.add_column(
        "subscription",
        sa.Column("frequency", sa.String(8), nullable=False, server_default="weekly"),
    )
    op.add_column(
        "subscription", sa.Column("paused", sa.Boolean(), nullable=False, server_default="false")
    )
    op.create_check_constraint(
        "ck_subscription_min_fit", "subscription", "min_fit >= 0.5 AND min_fit <= 0.95"
    )
    op.create_check_constraint(
        "ck_subscription_frequency", "subscription", "frequency IN ('daily', 'weekly')"
    )
    op.create_table(
        "alert_sent",
        sa.Column(
            "subscription_id",
            sa.Integer(),
            sa.ForeignKey("subscription.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("pub_no", sa.String(20), primary_key=True),
        sa.Column("fit", sa.Float(), nullable=False),
        sa.Column(
            "sent_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_table(
        "alert_exclusion",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "subscription_id",
            sa.Integer(),
            sa.ForeignKey("subscription.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("pub_no", sa.String(20), nullable=True),
        sa.Column("cpv_group", sa.String(3), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False
        ),
    )
    op.create_index("ix_alert_exclusion_subscription_id", "alert_exclusion", ["subscription_id"])


def downgrade() -> None:
    op.drop_index("ix_alert_exclusion_subscription_id", table_name="alert_exclusion")
    op.drop_table("alert_exclusion")
    op.drop_table("alert_sent")
    op.drop_constraint("ck_subscription_frequency", "subscription")
    op.drop_constraint("ck_subscription_min_fit", "subscription")
    for col in ("paused", "frequency", "cpv_divisions", "counties", "min_value_eur", "min_fit"):
        op.drop_column("subscription", col)
