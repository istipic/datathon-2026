"""Throwaway apps built with create_app: health, problem+json, headers, CORS, rate limit."""

from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime

import pytest
from fastapi import APIRouter, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from opendata_core.app_factory import create_app
from opendata_core.config import CoreSettings
from opendata_core.provenance import AccessMethod, IngestionRun, RunStatus, Tier, register_source

ORIGIN = "https://blizu.example.org"


def _router() -> APIRouter:
    r = APIRouter()

    @r.get("/api/v1/boom")
    def boom() -> None:
        raise RuntimeError("secret internals")

    @r.get("/api/v1/teapot")
    def teapot() -> None:
        raise HTTPException(418, "I am a teapot", headers={"X-Custom": "1"})

    @r.get("/api/v1/items/{item_id}")
    def item(item_id: int) -> dict[str, int]:
        return {"id": item_id}

    return r


def _dep(session: Session) -> Callable[[], Iterator[Session]]:
    def get_session() -> Iterator[Session]:
        yield session

    return get_session


def _client(settings: CoreSettings, session: Session | None = None, **kw: object) -> TestClient:
    app = create_app(
        settings,
        [_router()],
        [ORIGIN],
        get_session=_dep(session) if session is not None else None,
        **kw,  # type: ignore[arg-type]
    )
    return TestClient(app, raise_server_exceptions=False)


def test_health_returns_200_with_db(settings: CoreSettings, session: Session) -> None:
    r = _client(settings.model_copy(update={"git_sha": "abc123"}), session).get("/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"
    assert body["git_sha"] == "abc123"
    assert body["version"]
    assert datetime.fromisoformat(body["time"]).tzinfo is not None


def test_health_without_database_configured(settings: CoreSettings) -> None:
    r = _client(settings).get("/health")
    assert r.status_code == 200
    assert r.json()["db"] == "not_configured"
    assert _client(settings).get("/api/v1/sources").json()["sources"] == []


def test_health_reports_503_when_db_down(settings: CoreSettings, session: Session) -> None:
    session.get_bind().dispose()
    session.close()
    broken = Session(bind=_BrokenEngine())  # type: ignore[arg-type]
    r = _client(settings, broken).get("/health")
    assert r.status_code == 503
    assert r.json()["db"] == "error"
    assert r.json()["status"] == "degraded"


class _BrokenEngine:
    """Minimal bind whose connections always fail."""

    def __getattr__(self, name: str) -> object:
        raise RuntimeError("db down")


def test_forced_404_is_problem_json(settings: CoreSettings) -> None:
    r = _client(settings).get("/api/v1/does-not-exist")
    assert r.status_code == 404
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["status"] == 404
    assert body["title"] == "Not Found"
    assert body["type"] == "about:blank"
    assert body["instance"] == "/api/v1/does-not-exist"
    assert body["request_id"] == r.headers["x-request-id"]


def test_http_exception_keeps_detail_and_headers(settings: CoreSettings) -> None:
    r = _client(settings).get("/api/v1/teapot")
    assert r.status_code == 418
    assert r.json()["detail"] == "I am a teapot"
    assert r.headers["x-custom"] == "1"
    assert r.headers["content-type"].startswith("application/problem+json")


def test_validation_error_is_422_problem_json(settings: CoreSettings) -> None:
    r = _client(settings).get("/api/v1/items/abc")
    assert r.status_code == 422
    assert r.headers["content-type"].startswith("application/problem+json")
    body = r.json()
    assert body["title"] == "Validation Error"
    assert body["errors"][0]["loc"] == ["path", "item_id"]
    assert _client(settings).get("/api/v1/items/7").json() == {"id": 7}


def test_unhandled_error_dev_includes_traceback(settings: CoreSettings) -> None:
    r = _client(settings).get("/api/v1/boom")
    assert r.status_code == 500
    assert r.headers["content-type"].startswith("application/problem+json")
    assert "secret internals" in r.json()["detail"]
    assert "traceback" in r.json()


def test_unhandled_error_prod_hides_internals(settings: CoreSettings) -> None:
    r = _client(settings.model_copy(update={"env": "prod"})).get("/api/v1/boom")
    assert r.status_code == 500
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.json()["detail"] == "Internal server error"
    assert "traceback" not in r.json()
    assert "secret internals" not in r.text
    assert "Traceback" not in r.text


def test_prod_disables_docs(settings: CoreSettings) -> None:
    prod = _client(settings.model_copy(update={"env": "prod"}))
    assert prod.get("/docs").status_code == 404
    assert prod.get("/openapi.json").status_code == 404
    assert _client(settings).get("/openapi.json").status_code == 200


def test_security_headers_present(settings: CoreSettings) -> None:
    r = _client(settings).get("/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert r.headers["permissions-policy"] == "geolocation=(self)"
    # also on error responses
    assert _client(settings).get("/nope").headers["x-content-type-options"] == "nosniff"


def test_cors_only_for_listed_origins(settings: CoreSettings) -> None:
    c = _client(settings)
    ok = c.get("/health", headers={"Origin": ORIGIN})
    assert ok.headers["access-control-allow-origin"] == ORIGIN
    bad = c.get("/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in bad.headers


def test_wildcard_cors_is_rejected(settings: CoreSettings) -> None:
    with pytest.raises(ValueError, match="wildcard"):
        create_app(settings, [], ["*"])


def test_rate_limit_60_per_minute_returns_problem_json(settings: CoreSettings) -> None:
    c = _client(settings)
    codes = [c.get("/api/v1/items/1").status_code for _ in range(60)]
    assert set(codes) == {200}
    r = c.get("/api/v1/items/1")
    assert r.status_code == 429
    assert r.headers["content-type"].startswith("application/problem+json")
    assert r.headers["retry-after"]


def test_rate_limit_is_one_budget_per_ip_across_routes(settings: CoreSettings) -> None:
    c = _client(settings)
    for _ in range(30):
        assert c.get("/health").status_code == 200
        assert c.get("/api/v1/items/1").status_code == 200
    assert c.get("/health").status_code == 429


def test_sources_endpoint_lists_registered_sources(
    settings: CoreSettings, session: Session
) -> None:
    register_source(
        session,
        id="demo",
        title="Demo set",
        publisher="Publisher",
        url="https://example.org",
        access_method=AccessMethod.api,
        tier=Tier.official,
    )
    now = datetime.now(UTC)
    session.add(
        IngestionRun(source_id="demo", started_at=now, finished_at=now, status=RunStatus.ok, rows=3)
    )
    session.commit()
    r = _client(settings, session).get("/api/v1/sources")
    assert r.status_code == 200
    body = r.json()
    [item] = body["sources"]
    assert item["id"] == "demo"
    assert item["freshness_days"] == 0
    assert item["last_run"]["rows"] == 3
    assert body["generated_at"]


def test_custom_title(settings: CoreSettings) -> None:
    c = _client(settings, title="Blizu API")
    assert c.get("/openapi.json").json()["info"]["title"] == "Blizu API"


def test_lifespan_runs_at_startup_and_shutdown(settings: CoreSettings) -> None:
    from contextlib import asynccontextmanager

    events: list[str] = []

    @asynccontextmanager
    async def lifespan(app: object):  # type: ignore[no-untyped-def]
        events.append("start")
        yield
        events.append("stop")

    app = create_app(settings, [], [ORIGIN], lifespan=lifespan)
    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert events == ["start"]
    assert events == ["start", "stop"]


def test_rate_limit_is_configurable(settings: CoreSettings) -> None:
    c = _client(settings.model_copy(update={"rate_limit": "5/minute"}))
    assert [c.get("/api/v1/items/1").status_code for _ in range(5)] == [200] * 5
    assert c.get("/api/v1/items/1").status_code == 429
