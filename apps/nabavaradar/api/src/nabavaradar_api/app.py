"""Application factory for the NabavaRadar API."""

from __future__ import annotations

import threading
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI
from sqlalchemy.orm import Session, sessionmaker

from nabavaradar_api.api import make_router
from nabavaradar_api.company import LookupQueue
from nabavaradar_api.match import MatchEngine
from nabavaradar_api.settings import NabavaSettings
from opendata_core.app_factory import create_app

log = structlog.get_logger(__name__)


def create_nabava_app(
    settings: NabavaSettings,
    get_session: Callable[..., Any],
    session_factory: sessionmaker[Session],
    *,
    extra_routers: list[Any] | None = None,
) -> FastAPI:
    """Build the app; the open-notice index is warmed in the background at start-up."""
    engine = MatchEngine()
    lookup = LookupQueue(settings, session_factory)

    def warm() -> None:
        try:
            with session_factory() as session:
                idx = engine.index(session)
            log.info("nabavaradar_index_ready", open_notices=len(idx.rows))
        except Exception as exc:  # noqa: BLE001 - data not ingested yet: serve /health and sources
            log.error("nabavaradar_index_not_loaded", error=str(exc)[:300])

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.engine = engine
        app.state.lookup = lookup
        threading.Thread(target=warm, daemon=True).start()
        yield

    routers = [make_router(get_session, settings, engine, lookup), *(extra_routers or [])]
    return create_app(
        settings,
        routers,
        settings.cors_origin_list,
        get_session=get_session,
        title="NabavaRadar API",
        lifespan=lifespan,
    )
