# ADR 0004: Own per-IP rate-limit middleware on top of slowapi

- Status: accepted
- Date: 2026-11-03

## Context

The spec asks for "slowapi default 60/minute per IP". With slowapi 0.1.10 and FastAPI 0.162,
`SlowAPIMiddleware` did **not limit anything**: the test `test_rate_limit_60_per_minute_returns_problem_json`
sent 61 requests and got 200 for all of them. Cause: slowapi's middleware finds the route handler
via `route.endpoint`, but routers added with `include_router` are wrapped in an object without
`endpoint` in this FastAPI version, so every route is treated as exempt.
A second pitfall: slowapi's default `key_style="url"` counts per URL path, so varying the path
would bypass the limit.

## Decision

`opendata_core.app_factory.PerIPRateLimitMiddleware` performs slowapi's own check
(`slowapi.middleware.async_check_limits`) with a fixed stub handler, and the `Limiter` uses
`key_style="endpoint"`. Result: exactly one 60/minute budget per client IP across all routes, a 429
`application/problem+json` response with `Retry-After`, and no dependency on route discovery.
Tests: 60 × 200 then 429; one shared budget across `/health` and `/api/v1/…`.

## Consequences

- It uses slowapi's `_inject_headers` (private) like slowapi's own middleware does; re-check on slowapi upgrades.
- Counters are in-memory per process (single uvicorn worker per container). Behind Caddy the API
  must run with `--proxy-headers` so the client IP, not the proxy's, is the key (done in
  `infra/python-api.Dockerfile`).
