"""The Alembic template (env.py.template + provenance_migration) must work on real PostgreSQL."""

from __future__ import annotations

import os
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config

import opendata_core.alembic_template as template_pkg

CORE_TABLES = {"data_source", "ingestion_run", "geocode_cache"}


@pytest.mark.db
def test_app_can_include_core_migration_and_roll_back(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    url = os.environ["TEST_DATABASE_URL"]
    migrations = tmp_path / "migrations"
    (migrations / "versions").mkdir(parents=True)
    # What an app does: copy env.py.template and add a revision that reuses the core migration.
    template = Path(template_pkg.__file__).parent / "env.py.template"
    (migrations / "env.py").write_text(template.read_text(encoding="utf-8"), encoding="utf-8")
    (migrations / "versions" / "0001_core.py").write_text(
        'revision = "0001"\n'
        "down_revision = None\n"
        "from opendata_core.alembic_template.provenance_migration import downgrade, upgrade\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("DATABASE_URL", url)
    monkeypatch.chdir(tmp_path)  # CoreSettings reads .env from the cwd; there is none here

    engine = sa.create_engine(url)
    with engine.begin() as conn:  # clean slate
        for name in (*CORE_TABLES, "alembic_version"):
            conn.execute(sa.text(f'DROP TABLE IF EXISTS "{name}" CASCADE'))

    cfg = Config()
    cfg.set_main_option("script_location", str(migrations))
    try:
        command.upgrade(cfg, "head")
        insp = sa.inspect(engine)
        assert set(insp.get_table_names()) >= CORE_TABLES
        geocode_cols = {c["name"]: c["type"] for c in insp.get_columns("geocode_cache")}
        assert type(geocode_cols["response"]).__name__ == "JSONB"  # Postgres variant is used
        command.downgrade(cfg, "base")
        assert not (CORE_TABLES & set(sa.inspect(engine).get_table_names()))
    finally:
        with engine.begin() as conn:
            for name in (*CORE_TABLES, "alembic_version"):
                conn.execute(sa.text(f'DROP TABLE IF EXISTS "{name}" CASCADE'))
        engine.dispose()
