"""``GET /health`` and ``GET /api/v1/sources`` router."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from importlib import metadata
from typing import Any

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.orm import Session

from opendata_core.config import CoreSettings
from opendata_core.provenance import sources_summary


def _version() -> str:
    try:
        return metadata.version("opendata-core")
    except metadata.PackageNotFoundError:  # pragma: no cover
        return "unknown"


def make_health_router(
    get_session: Callable[..., Any] | None, settings: CoreSettings | None = None
) -> APIRouter:
    """Build the router. ``get_session`` is a FastAPI dependency yielding a ``Session``.

    With ``get_session=None`` (no database configured) ``/health`` reports ``db: "not_configured"``
    and ``/api/v1/sources`` returns an empty list.
    """
    settings = settings or CoreSettings()
    router = APIRouter()
    dep = Depends(get_session) if get_session is not None else None

    def _health(session: Session | None) -> JSONResponse:
        body: dict[str, Any] = {
            "status": "ok",
            "db": "not_configured",
            "version": _version(),
            "git_sha": settings.git_sha,
            "time": datetime.now(UTC).isoformat(),
        }
        status = 200
        if session is not None:
            try:
                session.execute(text("select 1"))
                body["db"] = "ok"
            except Exception:
                body["status"] = "degraded"
                body["db"] = "error"
                status = 503
        return JSONResponse(body, status_code=status)

    def _sources(session: Session | None) -> dict[str, Any]:
        items = sources_summary(session) if session is not None else []
        return {"sources": items, "generated_at": datetime.now(UTC).isoformat()}

    if dep is not None:

        @router.get("/health", tags=["meta"])
        def health(session: Session = dep) -> JSONResponse:
            return _health(session)

        @router.get("/api/v1/sources", tags=["meta"])
        def sources(session: Session = dep) -> dict[str, Any]:
            return _sources(session)

    else:

        @router.get("/health", tags=["meta"])
        def health_no_db() -> JSONResponse:
            return _health(None)

        @router.get("/api/v1/sources", tags=["meta"])
        def sources_no_db() -> dict[str, Any]:
            return _sources(None)

    return router
