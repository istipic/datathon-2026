from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from opendata_core import http as h
from opendata_core.config import CoreSettings


def test_user_agent_format(settings: CoreSettings) -> None:
    assert h.user_agent(settings) == "datathon-test/0.1 (+mailto:test@example.org) datathon-2026"


def test_user_agent_requires_contact_email() -> None:
    s = CoreSettings(_env_file=None, contact_email="")  # type: ignore[call-arg]
    with pytest.raises(ValueError, match="CONTACT_EMAIL"):
        h.make_client(s)


@respx.mock
def test_client_sends_user_agent_and_timeouts(settings: CoreSettings) -> None:
    route = respx.get("https://x.test/a").respond(200, json={"ok": True})
    with h.make_client(settings) as client:
        assert client.timeout.connect == 5.0
        assert client.timeout.read == settings.http_timeout_s
        assert h.get_json(client, "https://x.test/a") == {"ok": True}
    assert route.calls.last.request.headers["user-agent"].startswith("datathon-test/0.1 (+mailto:")


@respx.mock
def test_retry_on_5xx_then_success(settings: CoreSettings, no_sleep: list[float]) -> None:
    route = respx.get("https://x.test/a").mock(
        side_effect=[httpx.Response(503), httpx.Response(502), httpx.Response(200, json=[1])]
    )
    with h.make_client(settings) as client:
        assert h.get_json(client, "https://x.test/a") == [1]
    assert route.call_count == 3
    assert no_sleep == [1.0, 2.0]  # exponential backoff 1 s, 2 s


@respx.mock
def test_gives_up_after_three_attempts(settings: CoreSettings, no_sleep: list[float]) -> None:
    route = respx.get("https://x.test/a").respond(500)
    with h.make_client(settings) as client, pytest.raises(httpx.HTTPStatusError) as err:
        h.get_bytes(client, "https://x.test/a")
    assert route.call_count == 3
    assert err.value.response.status_code == 500


@respx.mock
def test_retry_after_is_honoured(settings: CoreSettings, no_sleep: list[float]) -> None:
    respx.get("https://x.test/a").mock(
        side_effect=[
            httpx.Response(429, headers={"Retry-After": "5"}),
            httpx.Response(200, json={"a": 1}),
        ]
    )
    with h.make_client(settings) as client:
        assert h.get_json(client, "https://x.test/a") == {"a": 1}
    assert no_sleep == [5.0]


@respx.mock
def test_retry_on_timeout(settings: CoreSettings, no_sleep: list[float]) -> None:
    respx.get("https://x.test/a").mock(
        side_effect=[httpx.ReadTimeout("slow"), httpx.Response(200, json={"a": 1})]
    )
    with h.make_client(settings) as client:
        assert h.get_json(client, "https://x.test/a") == {"a": 1}
    assert len(no_sleep) == 1


@respx.mock
def test_4xx_is_not_retried(settings: CoreSettings, no_sleep: list[float]) -> None:
    route = respx.get("https://x.test/a").respond(404)
    with h.make_client(settings) as client, pytest.raises(httpx.HTTPStatusError):
        h.get_json(client, "https://x.test/a")
    assert route.call_count == 1
    assert no_sleep == []


@respx.mock
def test_post_json(settings: CoreSettings) -> None:
    route = respx.post("https://x.test/p").respond(200, json={"echo": 1})
    with h.make_client(settings) as client:
        assert h.post_json(client, "https://x.test/p", {"q": "a"}) == {"echo": 1}
    assert route.calls.last.request.content == b'{"q":"a"}'


@respx.mock
def test_cache_hit_keeps_original_retrieval_time(settings: CoreSettings) -> None:
    route = respx.get("https://x.test/a").respond(200, json={"v": 1})
    with h.make_client(settings) as client:
        first = h.fetch(
            client, "GET", "https://x.test/a", cache_dir=settings.http_cache_dir, cache_ttl_s=60
        )
        second = h.fetch(
            client, "GET", "https://x.test/a", cache_dir=settings.http_cache_dir, cache_ttl_s=60
        )
    assert route.call_count == 1
    assert not first.from_cache
    assert second.from_cache
    assert second.retrieved_at == first.retrieved_at
    assert second.json() == {"v": 1}


@respx.mock
def test_cache_expires(settings: CoreSettings) -> None:
    route = respx.get("https://x.test/a").respond(200, json={"v": 1})
    key = h.cache_key("GET", "https://x.test/a", None, None)
    with h.make_client(settings) as client:
        h.get_json(client, "https://x.test/a", cache_dir=settings.http_cache_dir, cache_ttl_s=60)
        meta = settings.http_cache_dir / f"{key}.meta.json"
        old = (datetime.now(UTC) - timedelta(seconds=120)).isoformat()
        meta.write_text(
            f'{{"url": "https://x.test/a", "status_code": 200, "retrieved_at": "{old}"}}'
        )
        h.get_json(client, "https://x.test/a", cache_dir=settings.http_cache_dir, cache_ttl_s=60)
    assert route.call_count == 2


@respx.mock
def test_errors_are_not_cached(settings: CoreSettings) -> None:
    respx.get("https://x.test/a").respond(404)
    with h.make_client(settings) as client, pytest.raises(httpx.HTTPStatusError):
        h.get_json(client, "https://x.test/a", cache_dir=settings.http_cache_dir, cache_ttl_s=60)
    assert (
        not list(settings.http_cache_dir.glob("*.bin"))
        if settings.http_cache_dir.exists()
        else True
    )


def test_cache_key_depends_on_all_parts() -> None:
    base = h.cache_key("GET", "u", {"a": 1}, None)
    assert base == h.cache_key("get", "u", {"a": 1}, None)
    assert base != h.cache_key("GET", "u", {"a": 2}, None)
    assert base != h.cache_key("POST", "u", {"a": 1}, None)
    assert base != h.cache_key("GET", "u", {"a": 1}, {"b": 1})
    assert base != h.cache_key("GET", "v", {"a": 1}, None)


def test_parse_retry_after() -> None:
    now = datetime(2026, 1, 1, tzinfo=UTC)
    assert h.parse_retry_after("7") == 7.0
    assert h.parse_retry_after(None) is None
    assert h.parse_retry_after("garbage") is None
    assert h.parse_retry_after("Thu, 01 Jan 2026 00:00:30 GMT", now=now) == 30.0
    assert h.parse_retry_after("Wed, 31 Dec 2025 23:00:00 GMT", now=now) == 0.0


@respx.mock
def test_download_file(settings: CoreSettings, tmp_path: Path) -> None:
    import hashlib

    payload = b"abc" * 1000
    respx.get("https://x.test/f.bin").respond(200, content=payload)
    with h.make_client(settings) as client:
        path, sha = h.download_file(client, "https://x.test/f.bin", tmp_path / "d" / "f.bin")
    assert path.read_bytes() == payload
    assert sha == hashlib.sha256(payload).hexdigest()
    assert not list(tmp_path.rglob("*.part"))


@respx.mock
def test_download_file_retries_and_cleans_up(
    settings: CoreSettings, tmp_path: Path, no_sleep: list[float]
) -> None:
    respx.get("https://x.test/f.bin").respond(503)
    with h.make_client(settings) as client, pytest.raises(httpx.HTTPStatusError):
        h.download_file(client, "https://x.test/f.bin", tmp_path / "f.bin")
    assert not (tmp_path / "f.bin").exists()
    assert not list(tmp_path.glob("*.part"))
    assert len(no_sleep) == 2


@respx.mock
def test_download_file_4xx_cleans_up(settings: CoreSettings, tmp_path: Path) -> None:
    respx.get("https://x.test/f.bin").respond(404)
    with h.make_client(settings) as client, pytest.raises(httpx.HTTPStatusError):
        h.download_file(client, "https://x.test/f.bin", tmp_path / "f.bin")
    assert not list(tmp_path.glob("*"))
