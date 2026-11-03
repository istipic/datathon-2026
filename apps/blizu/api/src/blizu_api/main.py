"""ASGI entry point: ``uvicorn blizu_api.main:app``."""

from __future__ import annotations

from sqlalchemy.orm import Session

from blizu_api.app import create_blizu_app
from blizu_api.settings import get_settings
from blizu_api.store import load_store
from opendata_core.db import make_engine, make_session_dependency

settings = get_settings()
_engine = make_engine(settings)
_get_session = make_session_dependency(_engine)


def _load() -> object:
    with Session(_engine) as session:
        return load_store(session, settings)


app = create_blizu_app(settings, _get_session, _load)  # type: ignore[arg-type]
