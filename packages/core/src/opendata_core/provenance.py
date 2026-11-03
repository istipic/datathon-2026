"""Data provenance: every externally loaded table has a ``data_source`` and ``ingestion_run``.

Rule: a loader registers its source with :func:`register_source` and wraps the load in
:func:`record_ingestion`. :func:`sources_summary` feeds ``GET /api/v1/sources`` and the UI.
"""

from __future__ import annotations

import enum
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column, relationship

from opendata_core.db import Base


class AccessMethod(enum.StrEnum):
    """How the data is obtained."""

    api = "api"
    download = "download"
    wms = "wms"
    derived = "derived"


class Tier(enum.StrEnum):
    """Trust tier of the source."""

    official = "official"
    eu_official = "eu_official"
    community = "community"
    derived = "derived"


class RunStatus(enum.StrEnum):
    """Outcome of an ingestion run."""

    ok = "ok"
    partial = "partial"
    failed = "failed"


def _enum(cls: type[enum.StrEnum], name: str) -> Enum:
    # Non-native enums (VARCHAR + CHECK) keep migrations simple and portable.
    return Enum(
        cls, name=name, native_enum=False, length=16, values_callable=lambda e: [m.value for m in e]
    )


class DataSource(Base):
    """A registered external (or derived) data source."""

    __tablename__ = "data_source"

    id: Mapped[str] = mapped_column(String(64), primary_key=True)  # slug
    title: Mapped[str] = mapped_column(Text)
    publisher: Mapped[str] = mapped_column(Text)
    url: Mapped[str] = mapped_column(Text)
    license_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    license_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    access_method: Mapped[AccessMethod] = mapped_column(_enum(AccessMethod, "access_method"))
    tier: Mapped[Tier] = mapped_column(_enum(Tier, "source_tier"))
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    runs: Mapped[list[IngestionRun]] = relationship(back_populates="source")


class IngestionRun(Base):
    """One attempt to load a source."""

    __tablename__ = "ingestion_run"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_id: Mapped[str] = mapped_column(ForeignKey("data_source.id"), index=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[RunStatus] = mapped_column(_enum(RunStatus, "run_status"))
    rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)
    source_last_modified: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    retrieved_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)

    source: Mapped[DataSource] = relationship(back_populates="runs")


def _utc(value: datetime | None) -> datetime | None:
    """Treat naive datetimes (e.g. from SQLite) as UTC."""
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


def register_source(
    session: Session,
    *,
    id: str,  # noqa: A002 - mirrors the column name
    title: str,
    publisher: str,
    url: str,
    access_method: AccessMethod,
    tier: Tier,
    license_name: str | None = None,
    license_url: str | None = None,
    notes: str | None = None,
) -> DataSource:
    """Insert or update a ``data_source`` row (idempotent) and flush it."""
    source = session.get(DataSource, id)
    if source is None:
        source = DataSource(id=id)
        session.add(source)
    source.title = title
    source.publisher = publisher
    source.url = url
    source.access_method = access_method
    source.tier = tier
    source.license_name = license_name
    source.license_url = license_url
    source.notes = notes
    session.flush()
    return source


@contextmanager
def record_ingestion(session: Session, source_id: str, url: str) -> Iterator[IngestionRun]:
    """Record an ingestion run around a load.

    The run row is committed *before* the body executes with status ``failed`` and
    ``error="run did not finish"`` so a crashed process leaves an honest trace. On normal exit
    the status becomes ``ok`` (or ``partial`` if the caller set ``run.status = RunStatus.partial``);
    on exception the session is rolled back, the run is marked ``failed`` with the error, and the
    exception is re-raised. The caller sets ``run.rows``, ``run.sha256`` and
    ``run.source_last_modified`` inside the block.
    """
    run = IngestionRun(
        source_id=source_id,
        started_at=datetime.now(UTC),
        status=RunStatus.failed,
        retrieved_url=url,
        error="run did not finish",
    )
    session.add(run)
    session.commit()
    run_id = run.id
    run.error = None
    run.status = RunStatus.ok  # optimistic; downgraded below on failure
    try:
        yield run
    except BaseException as exc:
        session.rollback()
        failed = session.get(IngestionRun, run_id)
        assert failed is not None
        failed.status = RunStatus.failed
        failed.finished_at = datetime.now(UTC)
        failed.error = f"{type(exc).__name__}: {exc}"[:2000]
        session.commit()
        raise
    else:
        run.finished_at = datetime.now(UTC)
        session.commit()


def sources_summary(session: Session, now: datetime | None = None) -> list[dict[str, Any]]:
    """Summarise every source for ``GET /api/v1/sources``.

    Each item holds the source metadata, ``last_run`` (the latest run with status ``ok``, or
    ``None``), ``retrieved_at`` and ``freshness_days``. ``freshness_days`` is the age of the *data*:
    days since ``source_last_modified`` when the publisher reports it, otherwise days since
    retrieval. It is ``None`` when the source was never loaded successfully.
    """
    now = now or datetime.now(UTC)
    out: list[dict[str, Any]] = []
    for source in session.scalars(select(DataSource).order_by(DataSource.id)):
        last_ok = session.scalars(
            select(IngestionRun)
            .where(IngestionRun.source_id == source.id, IngestionRun.status == RunStatus.ok)
            .order_by(IngestionRun.finished_at.desc(), IngestionRun.id.desc())
            .limit(1)
        ).first()
        item: dict[str, Any] = {
            "id": source.id,
            "title": source.title,
            "publisher": source.publisher,
            "url": source.url,
            "license_name": source.license_name,
            "license_url": source.license_url,
            "access_method": source.access_method.value,
            "tier": source.tier.value,
            "notes": source.notes,
            "last_run": None,
            "retrieved_at": None,
            "freshness_days": None,
        }
        if last_ok is not None:
            retrieved = _utc(last_ok.finished_at)
            modified = _utc(last_ok.source_last_modified)
            basis = modified or retrieved
            item["last_run"] = {
                "id": last_ok.id,
                "rows": last_ok.rows,
                "sha256": last_ok.sha256,
                "retrieved_url": last_ok.retrieved_url,
                "source_last_modified": modified.isoformat() if modified else None,
            }
            item["retrieved_at"] = retrieved.isoformat() if retrieved else None
            if basis is not None:
                item["freshness_days"] = max((now - basis).days, 0)
        out.append(item)
    return out
