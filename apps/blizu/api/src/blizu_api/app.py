"""Application factory for the Blizu API."""

from __future__ import annotations

import threading
from collections.abc import AsyncIterator, Callable
from contextlib import asynccontextmanager
from typing import Any

import structlog
from fastapi import FastAPI

from blizu_api.api import make_router
from blizu_api.planner import Planner
from blizu_api.search import CategorySearch
from blizu_api.settings import BlizuSettings
from blizu_api.store import DataStore
from opendata_core.app_factory import create_app

log = structlog.get_logger(__name__)


def create_blizu_app(
    settings: BlizuSettings,
    get_session: Callable[..., Any],
    store_loader: Callable[[], DataStore],
) -> FastAPI:
    """Build the app; ``store_loader`` is called once at start-up (in the lifespan)."""

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        store = store_loader()
        app.state.store = store
        app.state.planner = Planner(store)
        app.state.search = CategorySearch(use_semantic=settings.semantic_search)
        # load the (optional) semantic model in the background so the first /search is fast
        if settings.semantic_search:
            threading.Thread(target=app.state.search.warm_up, daemon=True).start()
        log.info("blizu_ready", candidates=len(app.state.planner.candidates))
        yield

    return create_app(
        settings,
        [make_router(get_session, settings)],
        settings.cors_origin_list,
        get_session=get_session,
        title="Blizu API",
        lifespan=lifespan,
    )
