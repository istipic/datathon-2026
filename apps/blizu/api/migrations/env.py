"""Alembic environment for Blizu (DATABASE_URL from env / .env via BlizuSettings)."""

from alembic import context
from sqlalchemy import create_engine

import blizu_api.db  # noqa: F401  (registers Blizu tables on the shared metadata)
import opendata_core.geocode  # noqa: F401  (geocode_cache)
import opendata_core.popgrid  # noqa: F401  (popgrid_cell)
from blizu_api.settings import BlizuSettings
from opendata_core.db import Base

target_metadata = Base.metadata
settings = BlizuSettings()


def run_migrations_online() -> None:
    if not settings.database_url:
        raise SystemExit("DATABASE_URL is not set")
    engine = create_engine(settings.database_url)
    with engine.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    raise SystemExit("offline mode is not supported")
run_migrations_online()
