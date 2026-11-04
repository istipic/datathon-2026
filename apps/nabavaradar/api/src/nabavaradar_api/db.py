"""Database models and session factory for Birokratko.

Only company-level data is stored: no natural persons (the public Sudreg service does not return
them, and ``tests/test_no_persons.py`` scans the company tables for person-name columns).
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from typing import Any

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    SmallInteger,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from nabavaradar_api.constants import EMBED_DIM
from nabavaradar_api.settings import NabavaSettings
from opendata_core.db import Base, make_engine

_JSON = JSON().with_variant(JSONB(), "postgresql")


class Company(Base):
    """An active legal entity from the Sudski registar (company-level fields only)."""

    __tablename__ = "company"

    oib: Mapped[str] = mapped_column(String(11), primary_key=True)
    mbs: Mapped[int] = mapped_column(BigInteger, index=True)
    name: Mapped[str] = mapped_column(Text)
    status: Mapped[int] = mapped_column(SmallInteger)  # 1 = active (Sudreg subjekti.status)
    county_code: Mapped[int | None] = mapped_column(SmallInteger, nullable=True, index=True)
    nuts3: Mapped[str | None] = mapped_column(String(5), nullable=True)
    updated_snapshot: Mapped[int] = mapped_column(Integer)  # Sudreg snapshot id the row is from
    snapshot_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class CompanyActivity(Base):
    """A business activity of a company that carries an NKD code."""

    __tablename__ = "company_activity"

    oib: Mapped[str] = mapped_column(
        ForeignKey("company.oib", ondelete="CASCADE"), primary_key=True
    )
    nkd_code: Mapped[str] = mapped_column(String(8), primary_key=True)
    nkd_version: Mapped[str] = mapped_column(String(16), primary_key=True)  # NKD 1994 / 2002 / 2007
    is_main: Mapped[bool] = mapped_column(Boolean, default=False)


class Nkd(Base):
    """NKD classification entry (all versions: codes differ between versions, hence the key)."""

    __tablename__ = "nkd"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)
    version: Mapped[str] = mapped_column(String(16), primary_key=True)
    sudreg_id: Mapped[int] = mapped_column(BigInteger, unique=True)
    label_hr: Mapped[str] = mapped_column(Text)
    embedding: Mapped[Any] = mapped_column(Vector(EMBED_DIM), nullable=True)


class Cpv(Base):
    """CPV 2008 code with Croatian and English labels."""

    __tablename__ = "cpv"

    code: Mapped[str] = mapped_column(String(8), primary_key=True)  # 8 digits, no check digit
    check_digit: Mapped[str | None] = mapped_column(String(1), nullable=True)
    label_hr: Mapped[str | None] = mapped_column(Text, nullable=True)
    label_en: Mapped[str] = mapped_column(Text)
    division: Mapped[str] = mapped_column(String(2), index=True)
    cpv_group: Mapped[str] = mapped_column(String(3), index=True)
    embedding: Mapped[Any] = mapped_column(Vector(EMBED_DIM), nullable=True)


class Notice(Base):
    """A TED notice (competition or result) with Croatia as buyer country."""

    __tablename__ = "notice"

    pub_no: Mapped[str] = mapped_column(String(20), primary_key=True)
    type: Mapped[str] = mapped_column(String(12), index=True)  # competition | result
    notice_type: Mapped[str] = mapped_column(String(16))  # cn-standard, can-standard, ...
    pub_date: Mapped[date] = mapped_column(Date, index=True)
    procedure_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    buyer_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    buyer_nuts: Mapped[str | None] = mapped_column(String(5), nullable=True)
    place_nuts: Mapped[str | None] = mapped_column(String(5), nullable=True)
    cpv_codes: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    cpv_main: Mapped[str | None] = mapped_column(String(8), nullable=True, index=True)
    title: Mapped[str | None] = mapped_column(Text, nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    deadline: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    value_eur: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    n_lots: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    url_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    url_pdf: Mapped[str | None] = mapped_column(Text, nullable=True)
    embedding: Mapped[Any] = mapped_column(Vector(EMBED_DIM), nullable=True)
    raw: Mapped[Any] = mapped_column(_JSON, default=dict)
    retrieved_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Award(Base):
    """Outcome of one lot of a result notice (one row per winner; ``seq`` 0 when there is none)."""

    __tablename__ = "award"

    pub_no: Mapped[str] = mapped_column(
        ForeignKey("notice.pub_no", ondelete="CASCADE"), primary_key=True
    )
    lot_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    seq: Mapped[int] = mapped_column(SmallInteger, primary_key=True, default=0)
    lot_status: Mapped[str | None] = mapped_column(
        String(16), nullable=True
    )  # selec-w | clos-nw ...
    winner_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    winner_national_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    received_submissions: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Crosswalk(Base):
    """Similarity of an NKD class to a CPV division/group (top-10 per NKD entry and level)."""

    __tablename__ = "crosswalk"

    nkd_code: Mapped[str] = mapped_column(String(8), primary_key=True)
    nkd_version: Mapped[str] = mapped_column(String(16), primary_key=True)
    cpv_level: Mapped[str] = mapped_column(String(8), primary_key=True)  # division | group
    rank: Mapped[int] = mapped_column(SmallInteger, primary_key=True)
    cpv_prefix: Mapped[str] = mapped_column(String(3))
    similarity: Mapped[float] = mapped_column(Numeric(6, 5))


class CompetitionStat(Base):
    """Competition per CPV group (3 digits) and NUTS2 over the result window."""

    __tablename__ = "competition_stat"

    cpv_group: Mapped[str] = mapped_column(String(3), primary_key=True)
    nuts2: Mapped[str] = mapped_column(String(4), primary_key=True)  # 'HR' = whole country
    n_awards: Mapped[int] = mapped_column(Integer)
    median_submissions: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    single_bid_share: Mapped[float | None] = mapped_column(Numeric(6, 5), nullable=True)
    window_start: Mapped[date] = mapped_column(Date)
    window_end: Mapped[date] = mapped_column(Date)


class Calibration(Base):
    """Small JSON values computed at ingest (activity-notice cosine percentiles, ...)."""

    __tablename__ = "calibration"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[Any] = mapped_column(_JSON)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class Subscription(Base):
    """Weekly e-mail digest subscription (double opt-in). Stores the e-mail address only."""

    __tablename__ = "subscription"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    email: Mapped[str] = mapped_column(String(320), index=True)
    oib: Mapped[str | None] = mapped_column(String(11), nullable=True)
    query: Mapped[str | None] = mapped_column(String(500), nullable=True)
    confirmed: Mapped[bool] = mapped_column(Boolean, default=False)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    consent_text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    last_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # threshold alerts (migration 0004): the fit a notice must reach, filters, frequency, pause switch
    min_fit: Mapped[float] = mapped_column(Float, default=0.75, server_default="0.75")
    min_value_eur: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)
    counties: Mapped[list[int]] = mapped_column(_JSON, default=list, server_default="[]")
    cpv_divisions: Mapped[list[str]] = mapped_column(_JSON, default=list, server_default="[]")
    # rows created before migration 0004 were weekly digests (server default); new sign-ups default to daily
    frequency: Mapped[str] = mapped_column(String(8), default="daily", server_default="weekly")
    paused: Mapped[bool] = mapped_column(Boolean, default=False, server_default="false")


class AlertSent(Base):
    """A notice that was e-mailed to a subscriber: it is never sent to the same subscriber twice."""

    __tablename__ = "alert_sent"

    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscription.id", ondelete="CASCADE"), primary_key=True
    )
    pub_no: Mapped[str] = mapped_column(String(20), primary_key=True)
    fit: Mapped[float] = mapped_column(Float)
    sent_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class AlertExclusion(Base):
    """ "Ne zanima me" of an alert subscriber: a procedure and/or a CPV group that is not offered again."""

    __tablename__ = "alert_exclusion"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    subscription_id: Mapped[int] = mapped_column(
        ForeignKey("subscription.id", ondelete="CASCADE"), index=True
    )
    pub_no: Mapped[str | None] = mapped_column(String(20), nullable=True)
    cpv_group: Mapped[str | None] = mapped_column(String(3), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class MunicipalContract(Base):
    """A row of a municipal contract register (P1), column-mapped by fuzzy header matching."""

    __tablename__ = "municipal_contract"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(String(160), index=True)  # CKAN resource id
    package: Mapped[str] = mapped_column(Text)
    predmet: Mapped[str | None] = mapped_column(Text, nullable=True)
    cpv: Mapped[str | None] = mapped_column(String(16), nullable=True)
    bidder: Mapped[str | None] = mapped_column(Text, nullable=True)
    bidder_oib: Mapped[str | None] = mapped_column(String(11), nullable=True, index=True)
    amount: Mapped[Decimal | None] = mapped_column(Numeric(16, 2), nullable=True)
    contract_date: Mapped[date | None] = mapped_column(Date, nullable=True)


def make_session_factory(settings: NabavaSettings) -> sessionmaker[Session]:
    """Session factory bound to ``settings.database_url``."""
    return sessionmaker(make_engine(settings), expire_on_commit=False)
