"""Application factory for the Birokratko API."""

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
from nabavaradar_api.sounding import cpv_index
from nabavaradar_api.sudreg.client import SudregClient
from opendata_core.app_factory import create_app

log = structlog.get_logger(__name__)


def create_nabava_app(
    settings: NabavaSettings,
    get_session: Callable[..., Any],
    session_factory: sessionmaker[Session],
    *,
    extra_routers: list[Any] | None = None,
    lookup_client: SudregClient | None = None,
) -> FastAPI:
    """Build the app; the open-notice index is warmed in the background at start-up."""
    engine = MatchEngine()
    lookup = LookupQueue(settings, session_factory, lookup_client)

    def warm() -> None:
        try:
            with session_factory() as session:
                idx = engine.index(session)
                cpv_index(session)
            log.info("nabavaradar_index_ready", open_notices=len(idx.rows))
            from opendata_core import semantic

            semantic.encode_queries(
                ["zagrijavanje modela"]
            )  # load the e5 model before the first request
            log.info("nabavaradar_model_ready")
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
        title="Birokratko API",
        lifespan=lifespan,
    )
