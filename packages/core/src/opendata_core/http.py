"""HTTP client factory with retries, Retry-After handling and an optional file cache.

Every response carries its retrieval time (``Fetched.retrieved_at``) so callers can show users
when data was obtained. Cached responses are flagged (``from_cache=True``) and keep the
*original* retrieval time — they are never presented as freshly fetched.
"""

from __future__ import annotations

import hashlib
import json
import os
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import httpx
from tenacity import (
    RetryCallState,
    Retrying,
    retry_if_exception_type,
    stop_after_attempt,
)

from opendata_core.config import CoreSettings

MAX_ATTEMPTS = 3
BACKOFF_MIN_S = 1.0
BACKOFF_MAX_S = 8.0
RETRY_AFTER_CAP_S = 60.0
_RETRY_STATUS = frozenset({429}) | frozenset(range(500, 600))

# Indirection so tests can run without really sleeping.
_sleep = time.sleep


class RetryableHTTPError(Exception):
    """Raised internally for 429/5xx responses so tenacity can retry them."""

    def __init__(self, response: httpx.Response) -> None:
        super().__init__(f"HTTP {response.status_code} for {response.request.url}")
        self.response = response
        self.retry_after_s = parse_retry_after(response.headers.get("Retry-After"))


@dataclass(frozen=True)
class Fetched:
    """A response body together with provenance metadata."""

    content: bytes
    status_code: int
    url: str
    retrieved_at: datetime
    from_cache: bool = False

    def json(self) -> Any:
        """Decode the body as JSON."""
        return json.loads(self.content)


def parse_retry_after(value: str | None, now: datetime | None = None) -> float | None:
    """Parse a ``Retry-After`` header (delta-seconds or HTTP-date) into seconds."""
    if not value:
        return None
    value = value.strip()
    if value.isdigit():
        return float(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    delta = (when - (now or datetime.now(UTC))).total_seconds()
    return max(delta, 0.0)


def user_agent(settings: CoreSettings) -> str:
    """Build the identifying User-Agent ``<app>/0.1 (+mailto:<email>) datathon-2026``."""
    if not settings.contact_email:
        raise ValueError(
            "CONTACT_EMAIL must be set: external sources require an identifying User-Agent"
        )
    return f"{settings.app_name}/0.1 (+mailto:{settings.contact_email}) datathon-2026"


def make_client(settings: CoreSettings) -> httpx.Client:
    """Create an ``httpx.Client`` with the project timeouts and identifying User-Agent."""
    return httpx.Client(
        timeout=httpx.Timeout(settings.http_timeout_s, connect=5.0),
        headers={"User-Agent": user_agent(settings)},
        follow_redirects=True,
    )


def _wait(retry_state: RetryCallState) -> float:
    """Exponential backoff 1-8 s, but never shorter than a server-sent Retry-After."""
    attempt = retry_state.attempt_number
    backoff = float(min(BACKOFF_MAX_S, max(BACKOFF_MIN_S, BACKOFF_MIN_S * 2 ** (attempt - 1))))
    outcome = retry_state.outcome
    exc = outcome.exception() if outcome else None
    if isinstance(exc, RetryableHTTPError) and exc.retry_after_s is not None:
        return float(min(max(backoff, exc.retry_after_s), RETRY_AFTER_CAP_S))
    return backoff


def _retrying() -> Retrying:
    return Retrying(
        stop=stop_after_attempt(MAX_ATTEMPTS),
        wait=_wait,
        retry=retry_if_exception_type(
            (httpx.TimeoutException, httpx.TransportError, RetryableHTTPError)
        ),
        sleep=lambda s: _sleep(s),
        reraise=True,
    )


# --------------------------------------------------------------------------- cache


def cache_key(method: str, url: str, params: Mapping[str, Any] | None, body: Any) -> str:
    """sha256 of method + url + params + body (canonical JSON, sorted keys)."""
    payload = json.dumps(
        [method.upper(), url, params or {}, body], sort_keys=True, default=str, ensure_ascii=True
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def _cache_read(cache_dir: Path, key: str, ttl_s: float) -> Fetched | None:
    meta_path = cache_dir / f"{key}.meta.json"
    body_path = cache_dir / f"{key}.bin"
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
        retrieved_at = datetime.fromisoformat(meta["retrieved_at"])
        if (datetime.now(UTC) - retrieved_at).total_seconds() > ttl_s:
            return None
        return Fetched(
            content=body_path.read_bytes(),
            status_code=int(meta["status_code"]),
            url=str(meta["url"]),
            retrieved_at=retrieved_at,
            from_cache=True,
        )
    except (OSError, ValueError, KeyError):
        return None


def _cache_write(cache_dir: Path, key: str, fetched: Fetched) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    meta = {
        "url": fetched.url,
        "status_code": fetched.status_code,
        "retrieved_at": fetched.retrieved_at.isoformat(),
    }
    # Write body first, meta last: a half-written entry is simply ignored.
    tmp = cache_dir / f"{key}.bin.tmp"
    tmp.write_bytes(fetched.content)
    os.replace(tmp, cache_dir / f"{key}.bin")
    (cache_dir / f"{key}.meta.json").write_text(json.dumps(meta), encoding="utf-8")


# --------------------------------------------------------------------------- requests


def fetch(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    params: Mapping[str, Any] | None = None,
    json_body: Any = None,
    cache_dir: Path | None = None,
    cache_ttl_s: float | None = None,
) -> Fetched:
    """Perform a request with retries; optionally read/write the file cache.

    Retries (3 attempts, exponential backoff 1-8 s) on timeouts, transport errors, 429 and 5xx,
    honouring ``Retry-After``. Other 4xx responses raise ``httpx.HTTPStatusError`` at once.
    Only successful (2xx) responses are cached.
    """
    use_cache = cache_dir is not None and cache_ttl_s is not None and cache_ttl_s > 0
    key = cache_key(method, url, params, json_body)
    if use_cache:
        assert cache_dir is not None
        assert cache_ttl_s is not None
        hit = _cache_read(cache_dir, key, cache_ttl_s)
        if hit is not None:
            return hit

    def attempt() -> httpx.Response:
        response = client.request(method, url, params=params, json=json_body)
        if response.status_code in _RETRY_STATUS:
            raise RetryableHTTPError(response)
        response.raise_for_status()
        return response

    try:
        response = _retrying()(attempt)
    except RetryableHTTPError as exc:
        # Retries exhausted: surface as a regular HTTP error carrying the response.
        raise httpx.HTTPStatusError(
            str(exc), request=exc.response.request, response=exc.response
        ) from exc

    fetched = Fetched(
        content=response.content,
        status_code=response.status_code,
        url=str(response.url),
        retrieved_at=datetime.now(UTC),
    )
    if use_cache:
        assert cache_dir is not None
        _cache_write(cache_dir, key, fetched)
    return fetched


def get_json(
    client: httpx.Client,
    url: str,
    params: Mapping[str, Any] | None = None,
    *,
    cache_dir: Path | None = None,
    cache_ttl_s: float | None = None,
) -> Any:
    """GET and decode JSON."""
    return fetch(
        client, "GET", url, params=params, cache_dir=cache_dir, cache_ttl_s=cache_ttl_s
    ).json()


def get_bytes(
    client: httpx.Client,
    url: str,
    params: Mapping[str, Any] | None = None,
    *,
    cache_dir: Path | None = None,
    cache_ttl_s: float | None = None,
) -> bytes:
    """GET and return the raw body."""
    return fetch(
        client, "GET", url, params=params, cache_dir=cache_dir, cache_ttl_s=cache_ttl_s
    ).content


def post_json(
    client: httpx.Client,
    url: str,
    body: Any,
    params: Mapping[str, Any] | None = None,
    *,
    cache_dir: Path | None = None,
    cache_ttl_s: float | None = None,
) -> Any:
    """POST a JSON body and decode the JSON response."""
    return fetch(
        client,
        "POST",
        url,
        params=params,
        json_body=body,
        cache_dir=cache_dir,
        cache_ttl_s=cache_ttl_s,
    ).json()


def download_file(client: httpx.Client, url: str, dest: Path) -> tuple[Path, str]:
    """Stream ``url`` to ``dest`` (atomically) and return ``(dest, sha256)``.

    Retries the whole transfer on timeouts, transport errors, 429 and 5xx.
    """
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".part")

    def attempt() -> str:
        digest = hashlib.sha256()
        with client.stream("GET", url) as response:
            if response.status_code in _RETRY_STATUS:
                response.read()
                raise RetryableHTTPError(response)
            response.raise_for_status()
            with tmp.open("wb") as fh:
                for chunk in response.iter_bytes(chunk_size=1024 * 256):
                    fh.write(chunk)
                    digest.update(chunk)
        return digest.hexdigest()

    try:
        sha = _retrying()(attempt)
    except RetryableHTTPError as exc:
        tmp.unlink(missing_ok=True)
        raise httpx.HTTPStatusError(
            str(exc), request=exc.response.request, response=exc.response
        ) from exc
    except Exception:
        tmp.unlink(missing_ok=True)
        raise
    os.replace(tmp, dest)
    return dest, sha
