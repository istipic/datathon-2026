from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from sqlalchemy.orm import Session

import opendata_core.alembic_template.provenance_migration as mig
from opendata_core.db import Base
from opendata_core.provenance import (
    AccessMethod,
    DataSource,
    IngestionRun,
    RunStatus,
    Tier,
    record_ingestion,
    register_source,
    sources_summary,
)

NOW = datetime(2026, 11, 3, 12, 0, tzinfo=UTC)


def _src(session: Session, sid: str = "demo") -> DataSource:
    return register_source(
        session,
        id=sid,
        title="Demo",
        publisher="Pub",
        url="https://example.org",
        access_method=AccessMethod.api,
        tier=Tier.official,
        license_name="CC-BY 4.0",
    )


def test_register_source_is_idempotent(session: Session) -> None:
    _src(session)
    register_source(
        session,
        id="demo",
        title="Renamed",
        publisher="Pub",
        url="https://example.org",
        access_method=AccessMethod.download,
        tier=Tier.derived,
    )
    session.commit()
    rows = session.query(DataSource).all()
    assert len(rows) == 1
    assert rows[0].title == "Renamed"
    assert rows[0].access_method is AccessMethod.download
    assert rows[0].license_name is None


def test_record_ingestion_ok(session: Session) -> None:
    _src(session)
    session.commit()
    with record_ingestion(session, "demo", "https://example.org/file") as run:
        run.rows = 42
        run.sha256 = "ab" * 32
        run.source_last_modified = NOW - timedelta(days=3)
    saved = session.query(IngestionRun).one()
    assert saved.status is RunStatus.ok
    assert saved.rows == 42
    assert saved.error is None
    assert saved.finished_at is not None
    assert saved.started_at <= saved.finished_at
    assert saved.retrieved_url == "https://example.org/file"


def test_run_is_not_successful_while_in_progress(session: Session) -> None:
    _src(session)
    session.commit()
    with record_ingestion(session, "demo", "u") as run:
        session.commit()  # e.g. a nested context committing while this run is still open
        assert run.status is RunStatus.failed
        assert run.error == "run did not finish"
        assert run.finished_at is None
        assert sources_summary(session)[0]["last_run"] is None  # not counted as a successful load
    assert run.status is RunStatus.ok
    assert run.error is None


def test_record_ingestion_partial(session: Session) -> None:
    _src(session)
    session.commit()
    with record_ingestion(session, "demo", "u") as run:
        run.status = RunStatus.partial
        run.rows = 1
    assert session.query(IngestionRun).one().status is RunStatus.partial


def test_record_ingestion_failure_is_recorded_and_reraised(session: Session) -> None:
    _src(session)
    session.commit()

    def failing_load() -> None:
        with record_ingestion(session, "demo", "u"):
            session.add(
                DataSource(
                    id="half-loaded",
                    title="t",
                    publisher="p",
                    url="u",
                    access_method=AccessMethod.api,
                    tier=Tier.derived,
                )
            )
            raise RuntimeError("boom")

    with pytest.raises(RuntimeError, match="boom"):
        failing_load()
    run = session.query(IngestionRun).one()
    assert run.status is RunStatus.failed
    assert run.error == "RuntimeError: boom"
    assert run.finished_at is not None
    # the data written inside the block was rolled back
    assert session.get(DataSource, "half-loaded") is None


def test_sources_summary_without_runs(session: Session) -> None:
    _src(session)
    session.commit()
    [item] = sources_summary(session, now=NOW)
    assert item["id"] == "demo"
    assert item["access_method"] == "api"
    assert item["tier"] == "official"
    assert item["last_run"] is None
    assert item["freshness_days"] is None
    assert item["retrieved_at"] is None


def test_sources_summary_uses_last_successful_run(session: Session) -> None:
    _src(session)
    session.add_all(
        [
            IngestionRun(
                source_id="demo",
                started_at=NOW - timedelta(days=10),
                finished_at=NOW - timedelta(days=10),
                status=RunStatus.ok,
                rows=1,
                source_last_modified=NOW - timedelta(days=400),
            ),
            IngestionRun(
                source_id="demo",
                started_at=NOW - timedelta(days=2),
                finished_at=NOW - timedelta(days=2),
                status=RunStatus.ok,
                rows=7,
                sha256="cd" * 32,
                source_last_modified=NOW - timedelta(days=40),
                retrieved_url="https://example.org/f",
            ),
            IngestionRun(
                source_id="demo",
                started_at=NOW - timedelta(days=1),
                finished_at=NOW - timedelta(days=1),
                status=RunStatus.failed,
                error="x",
            ),
        ]
    )
    session.commit()
    [item] = sources_summary(session, now=NOW)
    assert item["last_run"]["rows"] == 7
    assert item["last_run"]["retrieved_url"] == "https://example.org/f"
    # freshness = age of the data (source_last_modified), not of the download
    assert item["freshness_days"] == 40
    assert item["retrieved_at"].startswith("2026-11-01")


def test_freshness_falls_back_to_retrieval_time(session: Session) -> None:
    _src(session)
    session.add(
        IngestionRun(
            source_id="demo",
            started_at=NOW - timedelta(days=5),
            finished_at=NOW - timedelta(days=5),
            status=RunStatus.ok,
        )
    )
    session.commit()
    [item] = sources_summary(session, now=NOW)
    assert item["freshness_days"] == 5
    assert item["last_run"]["source_last_modified"] is None


def test_migration_matches_orm_metadata() -> None:
    """The reusable Alembic migration must create the same columns as the ORM models."""
    engine = sa.create_engine("sqlite://")
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mig.upgrade()
    insp = sa.inspect(engine)
    for name in ("data_source", "ingestion_run", "geocode_cache"):
        orm_cols = {c.name for c in Base.metadata.tables[name].columns}
        db_cols = {c["name"] for c in insp.get_columns(name)}
        assert db_cols == orm_cols, name
        orm_pk = {c.name for c in Base.metadata.tables[name].primary_key.columns}
        assert set(insp.get_pk_constraint(name)["constrained_columns"]) == orm_pk
    with engine.begin() as conn:
        ctx = MigrationContext.configure(conn)
        with Operations.context(ctx):
            mig.downgrade()
    assert not sa.inspect(engine).get_table_names()
