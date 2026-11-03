"""FastAPI application factory shared by all three apps."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Sequence
from typing import Any

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter
from slowapi.middleware import async_check_limits
from slowapi.util import get_remote_address
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response
from starlette.types import Lifespan

from opendata_core.config import CoreSettings
from opendata_core.db import make_engine, make_session_dependency
from opendata_core.errors import register_exception_handlers
from opendata_core.health import make_health_router
from opendata_core.logging import RequestIDMiddleware, configure_logging

DEFAULT_RATE_LIMIT = "60/minute"
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "Referrer-Policy": "strict-origin-when-cross-origin",
    "Permissions-Policy": "geolocation=(self)",
}


def _per_ip_scope() -> None:
    """Stub handler: gives every route one shared per-IP counter (see PerIPRateLimitMiddleware)."""


class PerIPRateLimitMiddleware(BaseHTTPMiddleware):
    """Apply slowapi's default limit (60/minute per client IP) to every route.

    slowapi's own ``SlowAPIMiddleware`` looks up the route handler to decide what to limit, but
    with FastAPI >= 0.16x routers added via ``include_router`` are wrapped in an object without an
    ``endpoint`` attribute, so it finds no handler and silently exempts *everything* (verified by
    ``test_rate_limit_60_per_minute_returns_problem_json``). This middleware does the same check
    with a fixed stub handler, which also makes the limit a single per-IP budget. It awaits the
    app's own RateLimitExceeded handler, so the 429 is problem+json.
    """

    async def dispatch(
        self, request: Request, call_next: Callable[[Request], Awaitable[Response]]
    ) -> Response:
        limiter: Limiter = request.app.state.limiter
        if not limiter.enabled:
            return await call_next(request)
        error_response, inject_headers = await async_check_limits(
            limiter, request, _per_ip_scope, request.app
        )
        if error_response is not None:
            return error_response
        response = await call_next(request)
        if inject_headers:
            response = limiter._inject_headers(response, request.state.view_rate_limit)
        return response


async def _security_headers(
    request: Request, call_next: Callable[[Request], Awaitable[Response]]
) -> Response:
    response = await call_next(request)
    for name, value in SECURITY_HEADERS.items():
        response.headers.setdefault(name, value)
    return response


def create_app(
    settings: CoreSettings,
    routers: Sequence[APIRouter],
    cors_origins: Sequence[str],
    *,
    get_session: Callable[..., Any] | None = None,
    title: str | None = None,
    lifespan: Lifespan[FastAPI] | None = None,
) -> FastAPI:
    """Create an app with logging, problem+json errors, health, CORS, rate limit, security headers.

    Args:
        settings: app settings.
        routers: the app's own routers (included as given; use the ``/api/v1`` prefix).
        cors_origins: explicit allowed origins; ``"*"`` is rejected.
        get_session: FastAPI session dependency for ``/health`` and ``/api/v1/sources``. When
            omitted it is built from ``settings.database_url`` if set, else the DB is reported as
            ``not_configured``.
        title: OpenAPI title (defaults to ``settings.app_name``).
        lifespan: optional ASGI lifespan (e.g. to load data once at start-up).
    """
    if any(origin.strip() == "*" for origin in cors_origins):
        raise ValueError("wildcard CORS origins are not allowed; list origins explicitly")
    configure_logging(settings)

    if get_session is None and settings.database_url:
        get_session = make_session_dependency(make_engine(settings))

    app = FastAPI(
        title=title or settings.app_name,
        lifespan=lifespan,
        docs_url=None if settings.is_prod else "/docs",
        redoc_url=None,
        openapi_url=None if settings.is_prod else "/openapi.json",
    )
    # key_style="endpoint": one counter per IP (the default "url" style counts per path, which
    # would let a client dodge the limit by varying the URL).
    limiter = Limiter(
        key_func=get_remote_address, default_limits=[DEFAULT_RATE_LIMIT], key_style="endpoint"
    )
    app.state.limiter = limiter

    register_exception_handlers(app, settings)

    # Middleware: the last one added is the outermost.
    app.add_middleware(PerIPRateLimitMiddleware)
    app.middleware("http")(_security_headers)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(cors_origins),
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )
    app.add_middleware(RequestIDMiddleware)

    app.include_router(make_health_router(get_session, settings))
    for router in routers:
        app.include_router(router)
    return app
