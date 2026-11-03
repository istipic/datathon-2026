"""RFC 7807 ``application/problem+json`` error handlers."""

from __future__ import annotations

import http
import traceback
from typing import Any

import structlog
from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded
from starlette.exceptions import HTTPException as StarletteHTTPException

from opendata_core.config import CoreSettings

PROBLEM_JSON = "application/problem+json"
log = structlog.get_logger(__name__)


def problem(
    request: Request,
    status: int,
    title: str | None = None,
    detail: str | None = None,
    headers: dict[str, str] | None = None,
    **extra: Any,
) -> JSONResponse:
    """Build a problem+json response."""
    body: dict[str, Any] = {
        "type": "about:blank",
        "title": title or http.HTTPStatus(status).phrase,
        "status": status,
        "instance": request.url.path,
    }
    if detail is not None:
        body["detail"] = detail
    request_id = getattr(request.state, "request_id", None)
    if request_id:
        body["request_id"] = request_id
    body.update(extra)
    return JSONResponse(
        jsonable_encoder(body), status_code=status, media_type=PROBLEM_JSON, headers=headers
    )


def register_exception_handlers(app: FastAPI, settings: CoreSettings) -> None:
    """Install problem+json handlers for HTTP, validation, rate-limit and unhandled errors.

    In ``prod`` unhandled errors never expose exception text or stack traces.
    """

    async def http_exc(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, StarletteHTTPException)
        detail = exc.detail if isinstance(exc.detail, str) else None
        return problem(
            request, exc.status_code, detail=detail, headers=getattr(exc, "headers", None)
        )

    async def validation_exc(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RequestValidationError)
        return problem(
            request,
            422,
            title="Validation Error",
            detail="Request validation failed",
            errors=exc.errors(),
        )

    async def rate_limit_exc(request: Request, exc: Exception) -> JSONResponse:
        assert isinstance(exc, RateLimitExceeded)
        return problem(
            request, 429, detail=f"Rate limit exceeded: {exc.detail}", headers={"Retry-After": "60"}
        )

    async def unhandled_exc(request: Request, exc: Exception) -> JSONResponse:
        log.error("unhandled_exception", path=request.url.path, exc_info=exc)
        if settings.is_prod:
            return problem(request, 500, detail="Internal server error")
        return problem(
            request,
            500,
            detail=f"{type(exc).__name__}: {exc}",
            traceback=traceback.format_exception(exc),
        )

    app.add_exception_handler(StarletteHTTPException, http_exc)
    app.add_exception_handler(RequestValidationError, validation_exc)
    app.add_exception_handler(RateLimitExceeded, rate_limit_exc)
    app.add_exception_handler(Exception, unhandled_exc)
