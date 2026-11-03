from __future__ import annotations

import json

import pytest
import structlog
from fastapi import FastAPI
from fastapi.testclient import TestClient

from opendata_core.config import CoreSettings
from opendata_core.logging import REQUEST_ID_HEADER, RequestIDMiddleware, configure_logging


def test_settings_defaults_and_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("APP_NAME", "blizu")
    monkeypatch.setenv("ENV", "prod")
    monkeypatch.setenv("SMTP_PORT", "587")
    s = CoreSettings(_env_file=None)  # type: ignore[call-arg]
    assert s.app_name == "blizu"
    assert s.is_prod
    assert s.smtp_port == 587
    assert s.http_timeout_s == 20
    assert s.nominatim_url == "https://nominatim.openstreetmap.org"
    assert s.database_url is None


def test_settings_rejects_unknown_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("ENV", "staging")
    with pytest.raises(ValueError, match="env"):
        CoreSettings(_env_file=None)  # type: ignore[call-arg]


def test_prod_logs_are_json(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(CoreSettings(_env_file=None, env="prod", log_level="INFO"))  # type: ignore[call-arg]
    structlog.get_logger("t").info("hello", x=1)
    line = capsys.readouterr().err.strip().splitlines()[-1]
    data = json.loads(line)
    assert data["event"] == "hello"
    assert data["x"] == 1
    assert data["level"] == "info"
    assert data["timestamp"].endswith("Z")


def test_dev_logs_are_pretty(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(CoreSettings(_env_file=None, env="dev"))  # type: ignore[call-arg]
    structlog.get_logger("t").info("hello", x=1)
    out = capsys.readouterr().err
    assert "hello" in out
    with pytest.raises(json.JSONDecodeError):
        json.loads(out.strip().splitlines()[-1])


def test_log_level_filters(capsys: pytest.CaptureFixture[str]) -> None:
    configure_logging(CoreSettings(_env_file=None, env="prod", log_level="ERROR"))  # type: ignore[call-arg]
    structlog.get_logger("t").info("quiet")
    assert capsys.readouterr().err == ""


def _app() -> FastAPI:
    app = FastAPI()
    app.add_middleware(RequestIDMiddleware)

    @app.get("/x")
    def x() -> dict[str, str]:
        return {"request_id": structlog.contextvars.get_contextvars().get("request_id", "")}

    return app


def test_request_id_generated_and_bound() -> None:
    r = TestClient(_app()).get("/x")
    rid = r.headers[REQUEST_ID_HEADER]
    assert len(rid) == 32
    assert r.json()["request_id"] == rid


def test_request_id_is_propagated() -> None:
    r = TestClient(_app()).get("/x", headers={REQUEST_ID_HEADER: "abc-123"})
    assert r.headers[REQUEST_ID_HEADER] == "abc-123"


def test_unsafe_request_id_is_replaced() -> None:
    r = TestClient(_app()).get("/x", headers={REQUEST_ID_HEADER: "bad id\twith space"})
    assert r.headers[REQUEST_ID_HEADER] != "bad id\twith space"
    assert len(r.headers[REQUEST_ID_HEADER]) == 32
