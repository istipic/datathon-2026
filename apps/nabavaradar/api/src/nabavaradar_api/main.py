"""ASGI entry point: ``uvicorn nabavaradar_api.main:app``."""

from __future__ import annotations

from sqlalchemy.orm import sessionmaker

from nabavaradar_api.app import create_nabava_app
from nabavaradar_api.settings import get_settings
from opendata_core.db import make_engine, make_session_dependency

settings = get_settings()
_engine = make_engine(settings)
_get_session = make_session_dependency(_engine)
_factory = sessionmaker(_engine, expire_on_commit=False)

app = create_nabava_app(settings, _get_session, _factory)
