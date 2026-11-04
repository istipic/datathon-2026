"""Client for the Sudski registar open-data API (public service, OAuth2 client_credentials).

Facts taken from the official developer guide v3.0.0 and the OpenAPI spec v3.0.4 (data/evidence):

- token: ``POST <token_url>`` with HTTP Basic (client id/secret) and ``grant_type=client_credentials``;
  the response carries ``expires_in`` (21600 s on production, 3600 s on the test host), so the cache
  uses the value it is given;
- ``detalji_subjekta`` may be called at most 6 times per minute by public users;
- bulk tables take ``snapshot_id``, ``offset`` and ``limit`` and report ``X-Total-Count``; every
  request of one bulk run is pinned to a single snapshot;
- errors are ``{"error_code", "error_message", "log_id"}`` with HTTP 400 (user error) or 500.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from typing import Any

import httpx
import structlog

from nabavaradar_api.settings import NabavaSettings
from opendata_core.http import user_agent

log = structlog.get_logger(__name__)

DETALJI_LIMIT = 6  # requests ...
DETALJI_PERIOD_S = 60.0  # ... per minute (developer guide, "Ograničenja na broj upita")
TOKEN_SKEW_S = 60.0  # refresh a minute before expiry
PAGE_SIZE = 20_000


class SudregError(Exception):
    """Base class for Sudreg client errors."""


class SudregAuthError(SudregError):
    """Token refused (bad credentials) or data call unauthorised (account not verified)."""


class SudregNotFound(SudregError):
    """The register has no row for the request (``error_code`` 505, HTTP 400)."""


class RateLimited(SudregError):
    """A ``detalji_subjekta`` call would exceed the client-side limit; retry after ``retry_after``."""

    def __init__(self, retry_after: float) -> None:
        super().__init__(f"rate limited, retry in {retry_after:.0f} s")
        self.retry_after = retry_after


class SlidingWindowLimiter:
    """At most ``limit`` reservations in any window of ``period`` seconds (thread-safe).

    ``reserve()`` books the next free slot and returns how long to wait for it (0 when free), so
    callers can either sleep (CLI) or refuse and report ``Retry-After`` (API); ``peek()`` only asks.
    """

    def __init__(
        self,
        limit: int = DETALJI_LIMIT,
        period: float = DETALJI_PERIOD_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.limit = limit
        self.period = period
        self._clock = clock
        self._slots: deque[float] = deque()
        self._lock = threading.Lock()

    def _prune(self, now: float) -> None:
        while self._slots and self._slots[0] <= now - self.period:
            self._slots.popleft()

    def _wait_for(self, now: float) -> float:
        self._prune(now)
        if len(self._slots) < self.limit:
            return 0.0
        # the (len - limit + 1)-th oldest slot has to expire before a new one is free
        blocking = self._slots[len(self._slots) - self.limit]
        return max(0.0, blocking + self.period - now)

    def peek(self) -> float:
        """Seconds until a call would be allowed (0 = now), without booking."""
        with self._lock:
            return self._wait_for(self._clock())

    def reserve(self) -> float:
        """Book the next slot; returns the wait in seconds (0 = go now)."""
        with self._lock:
            now = self._clock()
            wait = self._wait_for(now)
            self._slots.append(now + wait)
            return wait


@dataclass
class Token:
    """A cached bearer token."""

    value: str
    expires_at: float


@dataclass
class Snapshot:
    """A register snapshot (``/snapshots``)."""

    id: int
    timestamp: str
    available_until: str | None
    staleness: int | None


class SudregClient:
    """Thin, testable client; inject ``http``/``clock``/``sleep`` in tests."""

    def __init__(
        self,
        settings: NabavaSettings,
        *,
        http: httpx.Client | None = None,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
        limiter: SlidingWindowLimiter | None = None,
    ) -> None:
        self.settings = settings
        self._owns_http = http is None
        self.http = http or httpx.Client(
            timeout=httpx.Timeout(60.0, connect=10.0),
            headers={"User-Agent": user_agent(settings)},
        )
        self._clock = clock
        self._sleep = sleep
        self.limiter = limiter or SlidingWindowLimiter(clock=clock)
        self._token: Token | None = None
        self._token_lock = threading.Lock()
        self.base = settings.sudreg_base_url.rstrip("/")

    # ------------------------------------------------------------------ lifecycle
    def close(self) -> None:
        """Close the HTTP client if this instance created it."""
        if self._owns_http:
            self.http.close()

    def __enter__(self) -> SudregClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # ------------------------------------------------------------------ token
    def token(self, *, force: bool = False) -> str:
        """Bearer token, cached until shortly before it expires."""
        with self._token_lock:
            now = self._clock()
            if not force and self._token and now < self._token.expires_at:
                return self._token.value
            secret = self.settings.sudreg_client_secret.get_secret_value()
            if not self.settings.sudreg_client_id or not secret:
                raise SudregAuthError("SUDREG_CLIENT_ID / SUDREG_CLIENT_SECRET are not set")
            response = self.http.post(
                self.settings.sudreg_token_url,
                auth=(self.settings.sudreg_client_id, secret),
                data={"grant_type": "client_credentials"},
            )
            if response.status_code in (400, 401, 403):
                raise SudregAuthError(f"token request refused (HTTP {response.status_code})")
            response.raise_for_status()
            body = response.json()
            ttl = float(body.get("expires_in", 3600))
            self._token = Token(body["access_token"], now + max(ttl - TOKEN_SKEW_S, 1.0))
            log.info("sudreg_token_refreshed", expires_in=ttl)  # never log the token itself
            return self._token.value

    # ------------------------------------------------------------------ requests
    def _get(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        url = f"{self.base}/{path.lstrip('/')}"
        for attempt in range(3):
            headers = {"Authorization": f"Bearer {self.token()}", "Accept": "application/json"}
            response = self.http.get(url, params=params, headers=headers)
            if response.status_code == 401 and attempt == 0:
                self.token(force=True)  # the token may have been revoked/expired early
                continue
            if response.status_code == 401:
                raise SudregAuthError(
                    "Sudreg refused the data call (401): the account's e-mail is probably not verified"
                )
            if response.status_code >= 500 and attempt < 2:
                self._sleep(2.0 * (attempt + 1))
                continue
            if response.status_code == 400:
                body = _safe_json(response)
                if isinstance(body, dict) and body.get("error_code") == 505:
                    raise SudregNotFound(str(body.get("error_message", "no rows")))
                raise SudregError(f"HTTP 400: {body}")
            response.raise_for_status()
            return response
        raise SudregError("unreachable")  # pragma: no cover

    def snapshots(self) -> list[Snapshot]:
        """Available snapshots, freshest first."""
        rows = self._get("snapshots").json()
        snaps = [
            Snapshot(r["id"], r["timestamp"], r.get("available_until"), r.get("staleness"))
            for r in rows
        ]
        return sorted(snaps, key=lambda s: (s.staleness if s.staleness is not None else 9999, -s.id))

    def table(
        self, name: str, snapshot_id: int, *, page_size: int = PAGE_SIZE, **params: Any
    ) -> Iterator[list[dict[str, Any]]]:
        """Pages of a bulk table, pinned to ``snapshot_id`` (offset/limit until X-Total-Count)."""
        offset = 0
        while True:
            response = self._get(
                name, {"snapshot_id": snapshot_id, "offset": offset, "limit": page_size, **params}
            )
            rows = response.json()
            if not rows:
                return
            yield rows
            offset += len(rows)
            total = response.headers.get("x-total-count")
            if len(rows) < page_size or (total is not None and offset >= int(total)):
                return

    def nkd_codes(self, snapshot_id: int) -> list[dict[str, Any]]:
        """The NKD code list (šifrarnik) as delivered by the register."""
        return self._get("nacionalna_klasifikacija_djelatnosti", {"snapshot_id": snapshot_id}).json()

    def detalji_subjekta(
        self, oib: str, *, snapshot_id: int | None = None, wait: bool = False
    ) -> dict[str, Any]:
        """All data of one subject by OIB. Limited to 6 calls/minute (client-side).

        With ``wait=False`` a call over the limit raises :class:`RateLimited` (nothing is booked);
        with ``wait=True`` it sleeps until a slot is free.
        """
        delay = self.limiter.reserve() if wait else self.limiter.peek()
        if delay > 0:
            if not wait:
                raise RateLimited(delay)
            self._sleep(delay)
        elif not wait:
            self.limiter.reserve()
        params: dict[str, Any] = {
            "tip_identifikatora": "oib",
            "identifikator": oib,
            "expand_relations": "true",
        }
        if snapshot_id is not None:
            params["snapshot_id"] = snapshot_id
        response = self._get("detalji_subjekta", params)
        body = response.json()
        body["_snapshot_id"] = response.headers.get("x-snapshot-id")
        body["_snapshot_timestamp"] = response.headers.get("x-timestamp")
        return body  # type: ignore[no-any-return]


def _safe_json(response: httpx.Response) -> Any:
    try:
        return response.json()
    except ValueError:
        return response.text[:200]
