"""NabavaRadar tables with pgvector HNSW indexes

Revision ID: 0002
Revises: 0001
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql

revision = "0002"
down_revision = "0001"

DIM = 384
JSON = sa.JSON().with_variant(postgresql.JSONB(), "postgresql")


def _hnsw(table: str) -> None:
    op.execute(
        f"CREATE INDEX idx_{table}_embedding_hnsw ON {table} "
        "USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64)"
    )


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table(
        "company",
        sa.Column("oib", sa.String(11), primary_key=True),
        sa.Column("mbs", sa.BigInteger, nullable=False),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("status", sa.SmallInteger, nullable=False),
        sa.Column("county_code", sa.SmallInteger),
        sa.Column("nuts3", sa.String(5)),
        sa.Column("updated_snapshot", sa.Integer, nullable=False),
        sa.Column("snapshot_at", sa.DateTime(timezone=True)),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_company_mbs", "company", ["mbs"])
    op.create_index("ix_company_county_code", "company", ["county_code"])

    op.create_table(
        "nkd",
        sa.Column("code", sa.String(8), primary_key=True),
        sa.Column("version", sa.String(16), primary_key=True),
        sa.Column("sudreg_id", sa.BigInteger, nullable=False, unique=True),
        sa.Column("label_hr", sa.Text, nullable=False),
        sa.Column("embedding", Vector(DIM)),
    )
    _hnsw("nkd")

    op.create_table(
        "company_activity",
        sa.Column("oib", sa.String(11), sa.ForeignKey("company.oib", ondelete="CASCADE"), primary_key=True),
        sa.Column("nkd_code", sa.String(8), primary_key=True),
        sa.Column("nkd_version", sa.String(16), primary_key=True),
        sa.Column("is_main", sa.Boolean, nullable=False),
    )

    op.create_table(
        "cpv",
        sa.Column("code", sa.String(8), primary_key=True),
        sa.Column("check_digit", sa.String(1)),
        sa.Column("label_hr", sa.Text),
        sa.Column("label_en", sa.Text, nullable=False),
        sa.Column("division", sa.String(2), nullable=False),
        sa.Column("cpv_group", sa.String(3), nullable=False),
        sa.Column("embedding", Vector(DIM)),
    )
    op.create_index("ix_cpv_division", "cpv", ["division"])
    op.create_index("ix_cpv_cpv_group", "cpv", ["cpv_group"])
    _hnsw("cpv")

    op.create_table(
        "notice",
        sa.Column("pub_no", sa.String(20), primary_key=True),
        sa.Column("type", sa.String(12), nullable=False),
        sa.Column("notice_type", sa.String(16), nullable=False),
        sa.Column("pub_date", sa.Date, nullable=False),
        sa.Column("procedure_id", sa.String(64)),
        sa.Column("buyer_name", sa.Text),
        sa.Column("buyer_nuts", sa.String(5)),
        sa.Column("place_nuts", sa.String(5)),
        sa.Column("cpv_codes", postgresql.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("cpv_main", sa.String(8)),
        sa.Column("title", sa.Text),
        sa.Column("description", sa.Text),
        sa.Column("deadline", sa.DateTime(timezone=True)),
        sa.Column("value_eur", sa.Numeric(16, 2)),
        sa.Column("currency", sa.String(3)),
        sa.Column("n_lots", sa.SmallInteger),
        sa.Column("url_html", sa.Text),
        sa.Column("url_pdf", sa.Text),
        sa.Column("embedding", Vector(DIM)),
        sa.Column("raw", JSON, nullable=False, server_default="{}"),
        sa.Column("retrieved_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_notice_type", "notice", ["type"])
    op.create_index("ix_notice_pub_date", "notice", ["pub_date"])
    op.create_index("ix_notice_procedure_id", "notice", ["procedure_id"])
    op.create_index("ix_notice_cpv_main", "notice", ["cpv_main"])
    op.create_index("ix_notice_deadline", "notice", ["deadline"])
    _hnsw("notice")
    op.execute(
        "CREATE INDEX idx_notice_fts ON notice USING gin "
        "(to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(description,'')))"
    )

    op.create_table(
        "award",
        sa.Column("pub_no", sa.String(20), sa.ForeignKey("notice.pub_no", ondelete="CASCADE"), primary_key=True),
        sa.Column("lot_id", sa.String(32), primary_key=True),
        sa.Column("seq", sa.SmallInteger, primary_key=True),
        sa.Column("lot_status", sa.String(16)),
        sa.Column("winner_name", sa.Text),
        sa.Column("winner_national_id", sa.String(32)),
        sa.Column("received_submissions", sa.Integer),
    )
    op.create_index("ix_award_winner_national_id", "award", ["winner_national_id"])

    op.create_table(
        "crosswalk",
        sa.Column("nkd_code", sa.String(8), primary_key=True),
        sa.Column("nkd_version", sa.String(16), primary_key=True),
        sa.Column("cpv_level", sa.String(8), primary_key=True),
        sa.Column("rank", sa.SmallInteger, primary_key=True),
        sa.Column("cpv_prefix", sa.String(3), nullable=False),
        sa.Column("similarity", sa.Numeric(6, 5), nullable=False),
    )

    op.create_table(
        "competition_stat",
        sa.Column("cpv_group", sa.String(3), primary_key=True),
        sa.Column("nuts2", sa.String(4), primary_key=True),
        sa.Column("n_awards", sa.Integer, nullable=False),
        sa.Column("median_submissions", sa.Numeric(8, 2)),
        sa.Column("single_bid_share", sa.Numeric(6, 5)),
        sa.Column("window_start", sa.Date, nullable=False),
        sa.Column("window_end", sa.Date, nullable=False),
    )

    op.create_table(
        "calibration",
        sa.Column("key", sa.String(64), primary_key=True),
        sa.Column("value", JSON, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )

    op.create_table(
        "subscription",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("email", sa.String(320), nullable=False),
        sa.Column("oib", sa.String(11)),
        sa.Column("query", sa.String(500)),
        sa.Column("confirmed", sa.Boolean, nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=False, unique=True),
        sa.Column("consent_text", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("last_sent_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_subscription_email", "subscription", ["email"])

    op.create_table(
        "municipal_contract",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("source_id", sa.String(160), nullable=False),
        sa.Column("package", sa.Text, nullable=False),
        sa.Column("predmet", sa.Text),
        sa.Column("cpv", sa.String(16)),
        sa.Column("bidder", sa.Text),
        sa.Column("bidder_oib", sa.String(11)),
        sa.Column("amount", sa.Numeric(16, 2)),
        sa.Column("contract_date", sa.Date),
    )
    op.create_index("ix_municipal_contract_source_id", "municipal_contract", ["source_id"])
    op.create_index("ix_municipal_contract_bidder_oib", "municipal_contract", ["bidder_oib"])


def downgrade() -> None:
    for table in (
        "municipal_contract",
        "subscription",
        "calibration",
        "competition_stat",
        "crosswalk",
        "award",
        "notice",
        "cpv",
        "company_activity",
        "nkd",
        "company",
    ):
        op.drop_table(table)
