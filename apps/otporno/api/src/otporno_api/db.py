"""Database models and session factory for Otporko."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from geoalchemy2 import Geometry
from sqlalchemy import (
    JSON,
    BigInteger,
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

from opendata_core.db import Base, make_engine
from otporno_api.settings import OtpornoSettings

_JSON = JSON().with_variant(JSONB(), "postgresql")


class Municipality(Base):
    """A Croatian city or municipality (GISCO LAU 2024)."""

    __tablename__ = "municipality"

    lau_id: Mapped[str] = mapped_column(String(16), primary_key=True)
    name: Mapped[str] = mapped_column(Text, index=True)
    geom: Mapped[Any] = mapped_column(Geometry("MULTIPOLYGON", srid=4326, spatial_index=True))
    area_km2: Mapped[float | None] = mapped_column(Float, nullable=True)
    attrs: Mapped[Any] = mapped_column(_JSON, default=dict)


class Cell(Base):
    """A 1 km Eurostat Census 2021 cell (the whole of Croatia) with its municipality."""

    __tablename__ = "cell"

    grd_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    geom: Mapped[Any] = mapped_column(Geometry("POLYGON", srid=4326, spatial_index=True))
    centroid: Mapped[Any] = mapped_column(Geometry("POINT", srid=4326, spatial_index=True))
    pop_total: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pop_65p: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lau_id: Mapped[str | None] = mapped_column(
        ForeignKey("municipality.lau_id"), nullable=True, index=True
    )


class FloodZone(Base):
    """Flood zone polygons per scenario. Only filled if Hrvatske vode publish vector data (ladder a);
    see docs/adr/0007 for why it is empty today."""

    __tablename__ = "flood_zone"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    scenario: Mapped[str] = mapped_column(String(8), index=True)  # high | medium | low
    geom: Mapped[Any] = mapped_column(Geometry("MULTIPOLYGON", srid=3765, spatial_index=True))


class FloodCell(Base):
    """Flood level of a cell (ladder a or b). Empty under ladder c."""

    __tablename__ = "flood_cell"

    grd_id: Mapped[str] = mapped_column(ForeignKey("cell.grd_id"), primary_key=True)
    level: Mapped[int] = mapped_column(SmallInteger)  # 0-3
    share_high: Mapped[float | None] = mapped_column(Float, nullable=True)
    share_medium: Mapped[float | None] = mapped_column(Float, nullable=True)
    share_low: Mapped[float | None] = mapped_column(Float, nullable=True)
    method: Mapped[str] = mapped_column(String(32))


class HeatPoint(Base):
    """Climate-model hot days / tropical nights for one coordinate and model (Open-Meteo)."""

    __tablename__ = "heat_point"

    lat_r: Mapped[float] = mapped_column(Numeric(6, 3), primary_key=True)
    lon_r: Mapped[float] = mapped_column(Numeric(6, 3), primary_key=True)
    model: Mapped[str] = mapped_column(String(32), primary_key=True)
    base_hot_days: Mapped[float | None] = mapped_column(Float, nullable=True)  # 1991-2020, per year
    fut_hot_days: Mapped[float | None] = mapped_column(Float, nullable=True)  # 2031-2050, per year
    base_trop_nights: Mapped[float | None] = mapped_column(Float, nullable=True)
    fut_trop_nights: Mapped[float | None] = mapped_column(Float, nullable=True)
    kind: Mapped[str] = mapped_column(
        String(8), default="address"
    )  # grid (future Tmax only) | address (full)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class HeatCell(Base):
    """Ensemble heat indicators of a cell, taken from the nearest 0.1 degree heat point."""

    __tablename__ = "heat_cell"

    grd_id: Mapped[str] = mapped_column(ForeignKey("cell.grd_id"), primary_key=True)
    base_mean: Mapped[float] = mapped_column(Float)
    fut_mean: Mapped[float] = mapped_column(Float)
    fut_min: Mapped[float] = mapped_column(Float)
    fut_max: Mapped[float] = mapped_column(Float)
    base_trop: Mapped[float | None] = mapped_column(Float, nullable=True)
    fut_trop: Mapped[float | None] = mapped_column(Float, nullable=True)
    percentile: Mapped[float] = mapped_column(Float)
    lat_r: Mapped[float] = mapped_column(Numeric(6, 3))
    lon_r: Mapped[float] = mapped_column(Numeric(6, 3))


class CandidateSite(Base):
    """A public building that could serve as a cooling centre (OSM)."""

    __tablename__ = "candidate_site"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lau_id: Mapped[str] = mapped_column(ForeignKey("municipality.lau_id"), index=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    kind: Mapped[str] = mapped_column(String(24))
    geom: Mapped[Any] = mapped_column(Geometry("POINT", srid=4326, spatial_index=True))
    source_id: Mapped[str] = mapped_column(ForeignKey("data_source.id"))
    osm_id: Mapped[str | None] = mapped_column(String(24), nullable=True)


class ActionRule(Base):
    """A cited recommendation shown on the passport / municipal brief."""

    __tablename__ = "action_rule"

    id: Mapped[str] = mapped_column(String(48), primary_key=True)
    hazard: Mapped[str] = mapped_column(String(12), index=True)  # flood | heat | fire
    band: Mapped[str] = mapped_column(String(16))
    audience: Mapped[str] = mapped_column(String(12))  # gradanin | opcina
    text_hr: Mapped[str] = mapped_column(Text)
    source_title: Mapped[str] = mapped_column(Text)
    source_url: Mapped[str] = mapped_column(Text)


class PrecomputeStatus(Base):
    """State of the per-municipality precompute (background task)."""

    __tablename__ = "precompute_status"

    lau_id: Mapped[str] = mapped_column(ForeignKey("municipality.lau_id"), primary_key=True)
    status: Mapped[str] = mapped_column(String(16))  # ready | computing | unavailable | failed
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)
    details: Mapped[Any] = mapped_column(_JSON, default=dict)


class ApiCallLog(Base):
    """Every Open-Meteo call with its rate-limit cost (the free tier is cost-limited, see ADR 0007)."""

    __tablename__ = "api_call_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    called_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), index=True
    )
    service: Mapped[str] = mapped_column(String(32))
    cost: Mapped[float] = mapped_column(Float)
    status: Mapped[int] = mapped_column(SmallInteger)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)


def make_session_factory(settings: OtpornoSettings) -> sessionmaker[Session]:
    """Session factory bound to ``settings.database_url``."""
    return sessionmaker(make_engine(settings), expire_on_commit=False)
