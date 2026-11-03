"""Database helpers for Blizu: models and session factory."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import JSON, DateTime, Float, ForeignKey, Integer, String, Text, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column, sessionmaker

from blizu_api.settings import BlizuSettings
from opendata_core.db import Base, make_engine

_JSON = JSON().with_variant(JSONB(), "postgresql")


class Facility(Base):
    """A public service point (official or OSM)."""

    __tablename__ = "facility"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    category: Mapped[str] = mapped_column(String(16), index=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    address: Mapped[str | None] = mapped_column(Text, nullable=True)
    geom: Mapped[Any] = mapped_column(Geometry("POINT", srid=4326, spatial_index=True))
    source_id: Mapped[str] = mapped_column(ForeignKey("data_source.id"))
    tier: Mapped[str] = mapped_column(String(16))
    source_record_id: Mapped[str | None] = mapped_column(Text, nullable=True)
    attrs: Mapped[Any] = mapped_column(_JSON, default=dict)
    loaded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class GtfsStopFrequency(Base):
    """Morning-peak departures per hour of a stop (or parent station)."""

    __tablename__ = "gtfs_stop_frequency"

    stop_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(Text)
    geom: Mapped[Any] = mapped_column(Geometry("POINT", srid=4326, spatial_index=True))
    dep_per_hour: Mapped[float] = mapped_column(Float)
    ref_date: Mapped[str] = mapped_column(String(10))
    feed_date: Mapped[str] = mapped_column(String(10))


class Cell(Base):
    """A 1 km Eurostat cell inside Grad Zagreb."""

    __tablename__ = "cell"

    grd_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    geom: Mapped[Any] = mapped_column(Geometry("POLYGON", srid=4326, spatial_index=True))
    pop_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pop_u15: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pop_65p: Mapped[int | None] = mapped_column(Integer, nullable=True)


class CellAccess(Base):
    """Mean walking minutes of a cell to the nearest facility, per persona and category."""

    __tablename__ = "cell_access"

    grd_id: Mapped[str] = mapped_column(ForeignKey("cell.grd_id"), primary_key=True)
    persona: Mapped[str] = mapped_column(String(16), primary_key=True)
    category: Mapped[str] = mapped_column(String(16), primary_key=True)
    mean_minutes: Mapped[float] = mapped_column(Float)


def make_session_factory(settings: BlizuSettings) -> sessionmaker[Session]:
    """Session factory bound to ``settings.database_url``."""
    return sessionmaker(make_engine(settings), expire_on_commit=False)
