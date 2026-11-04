"""Shared fixtures. DB tests need PostgreSQL with pgvector: set TEST_DATABASE_URL to a server URL, e.g.

    TEST_DATABASE_URL=postgresql+psycopg://postgres:<pw>@127.0.0.1:5432/postgres

A scratch database ``nabavaradar_test`` is created, migrated with Alembic and dropped afterwards;
no other database is touched.
"""

from __future__ import annotations

import os
from collections.abc import Iterator
from pathlib import Path

import psycopg
import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy.engine import make_url

API_DIR = Path(__file__).parents[1]
SCRATCH = "nabavaradar_test"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    if os.environ.get("TEST_DATABASE_URL"):
        return
    skip = pytest.mark.skip(reason="needs PostgreSQL with pgvector: set TEST_DATABASE_URL")
    for item in items:
        if "db" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(scope="session")
def test_db_url() -> Iterator[str]:
    """URL of a freshly migrated scratch database."""
    server = os.environ["TEST_DATABASE_URL"]
    url = make_url(server)
    admin = url.set(drivername="postgresql").render_as_string(hide_password=False)
    with psycopg.connect(admin, autocommit=True) as conn:
        conn.execute(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)")
        conn.execute(f"CREATE DATABASE {SCRATCH}")
    scratch = url.set(database=SCRATCH).render_as_string(hide_password=False)
    previous = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = scratch
    try:
        cfg = Config(str(API_DIR / "alembic.ini"))
        cfg.set_main_option("script_location", str(API_DIR / "migrations"))
        command.upgrade(cfg, "head")
        yield scratch
    finally:
        if previous is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = previous
        with psycopg.connect(admin, autocommit=True) as conn:
            conn.execute(f"DROP DATABASE IF EXISTS {SCRATCH} WITH (FORCE)")
