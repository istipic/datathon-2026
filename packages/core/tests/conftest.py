"""Shared fixtures and marker handling."""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

import opendata_core.db as core_db
import opendata_core.geocode  # noqa: F401  (registers geocode_cache on Base.metadata)
from opendata_core import http as http_mod
from opendata_core.config import CoreSettings

FIXTURES = Path(__file__).parent / "fixtures"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Skip ``live`` tests unless RUN_LIVE=1 and ``db`` tests unless TEST_DATABASE_URL is set."""
    skip_live = pytest.mark.skip(reason="live network test: set RUN_LIVE=1")
    skip_db = pytest.mark.skip(reason="needs PostGIS: set TEST_DATABASE_URL")
    for item in items:
        if "live" in item.keywords and os.environ.get("RUN_LIVE") != "1":
            item.add_marker(skip_live)
        if "db" in item.keywords and not os.environ.get("TEST_DATABASE_URL"):
            item.add_marker(skip_db)


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES


@pytest.fixture
def settings(tmp_path: Path) -> CoreSettings:
    """Settings that never read a developer's real .env."""
    return CoreSettings(
        _env_file=None,  # type: ignore[call-arg]
        app_name="datathon-test",
        env="dev",
        contact_email="test@example.org",
        http_cache_dir=tmp_path / "http-cache",
    )


@pytest.fixture
def no_sleep(monkeypatch: pytest.MonkeyPatch) -> list[float]:
    """Replace the retry sleep; returns the list of requested delays."""
    delays: list[float] = []
    monkeypatch.setattr(http_mod, "_sleep", delays.append)
    return delays


@pytest.fixture
def session() -> Iterator[Session]:
    """In-memory SQLite session with the core tables (no PostGIS tables)."""
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    tables = [t for name, t in core_db.Base.metadata.tables.items() if name != "popgrid_cell"]
    core_db.Base.metadata.create_all(engine, tables=tables)
    with Session(engine) as s:
        yield s
    engine.dispose()
