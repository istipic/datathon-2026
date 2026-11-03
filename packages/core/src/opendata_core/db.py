"""SQLAlchemy base class, engine/session helpers and a FastAPI session dependency."""

from __future__ import annotations

from collections.abc import Callable, Iterator

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from opendata_core.config import CoreSettings


class Base(DeclarativeBase):
    """Declarative base for tables defined in ``opendata_core``.

    Apps should include ``Base.metadata`` in their Alembic ``target_metadata`` (see
    ``opendata_core.alembic_template``).
    """


def make_engine(settings: CoreSettings) -> Engine:
    """Create an engine from ``settings.database_url`` (raises if it is not configured)."""
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not configured")
    return create_engine(settings.database_url, pool_pre_ping=True)


def make_session_dependency(engine: Engine) -> Callable[[], Iterator[Session]]:
    """Return a FastAPI dependency yielding a ``Session`` bound to ``engine``."""
    factory = sessionmaker(engine, expire_on_commit=False)

    def get_session() -> Iterator[Session]:
        with factory() as session:
            yield session

    return get_session
