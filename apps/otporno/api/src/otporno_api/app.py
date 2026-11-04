"""Application factory for the Otporko API."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastapi import FastAPI
from sqlalchemy.orm import Session, sessionmaker

from opendata_core.app_factory import create_app
from otporno_api.api import make_router
from otporno_api.settings import OtpornoSettings


def create_otporno_app(
    settings: OtpornoSettings,
    get_session: Callable[..., Any],
    factory: sessionmaker[Session],
) -> FastAPI:
    """Build the app (settings, session dependency, and the factory used by background tasks)."""
    return create_app(
        settings,
        [make_router(get_session, settings, factory)],
        settings.cors_origin_list,
        get_session=get_session,
        title="Otporko API",
    )
