"""ASGI entry point: ``uvicorn otporno_api.main:app``."""

from __future__ import annotations

from opendata_core.db import make_engine, make_session_dependency
from otporno_api.app import create_otporno_app
from otporno_api.db import make_session_factory
from otporno_api.settings import get_settings

settings = get_settings()
_engine = make_engine(settings)
_get_session = make_session_dependency(_engine)
app = create_otporno_app(settings, _get_session, make_session_factory(settings))
