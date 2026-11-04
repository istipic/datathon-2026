"""Alembic environment for Otporko (DATABASE_URL from env / .env via OtpornoSettings)."""

from alembic import context
from sqlalchemy import create_engine

import opendata_core.geocode  # noqa: F401  (geocode_cache)
import opendata_core.popgrid  # noqa: F401  (popgrid_cell)
import otporno_api.db  # noqa: F401  (registers the tables on the shared metadata)
from opendata_core.db import Base
from otporno_api.settings import OtpornoSettings

target_metadata = Base.metadata
settings = OtpornoSettings()


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
