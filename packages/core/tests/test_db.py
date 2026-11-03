from __future__ import annotations

import pytest
import sqlalchemy as sa
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from opendata_core.app_factory import create_app
from opendata_core.config import CoreSettings
from opendata_core.db import make_engine, make_session_dependency


def test_make_engine_requires_database_url(settings: CoreSettings) -> None:
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        make_engine(settings)


def test_make_engine_and_session_dependency(settings: CoreSettings) -> None:
    engine = make_engine(settings.model_copy(update={"database_url": "sqlite://"}))
    dependency = make_session_dependency(engine)
    gen = dependency()
    session = next(gen)
    assert isinstance(session, Session)
    assert session.execute(sa.text("select 1")).scalar() == 1
    gen.close()


def test_create_app_builds_session_from_database_url(settings: CoreSettings) -> None:
    app = create_app(
        settings.model_copy(update={"database_url": "sqlite://"}), [], ["https://a.example"]
    )
    # sources table does not exist in this in-memory DB, but "select 1" (health) works
    response = TestClient(app, raise_server_exceptions=False).get("/health")
    assert response.status_code == 200
    assert response.json()["db"] == "ok"
