"""Open-Meteo Climate API client that respects the free tier's *cost-based* limits.

Measured on 2026-11-04 (data/evidence/2026-11-04_open_meteo_climate_summary.json): the response carries
``x-ratelimit-cost`` (939.2 for 3 models x 2 variables x 21 915 days), ``x-ratelimit-limit: 600`` and
``x-ratelimit-window: 60``. The pricing page states 600 calls/minute, 5 000/hour and 10 000/day, so
only about ten full requests fit into a day: ``cost = series x days / 140``.

Every call is logged in ``api_call_log``; the rolling minute/hour/day usage is computed from that log, so
the limits hold across restarts. Batch jobs sleep until budget is free; interactive callers (the
``/passport`` endpoint) raise :class:`QuotaExceeded` when waiting would take too long.
"""

from __future__ import annotations

import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import structlog
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from opendata_core.http import user_agent
from otporno_api.db import ApiCallLog
from otporno_api.settings import OtpornoSettings

log = structlog.get_logger(__name__)

SERVICE = "open-meteo-climate"
COST_DIVISOR = 140.0  # cost = series x days / 140
LIMITS = (
    (60.0, 600.0),
    (3600.0, 5000.0),
    (86400.0, 10000.0),
)  # (window seconds, calls) per pricing page
SAFETY = 0.95  # stay below the published limits
MIN_INTERVAL_S = 1.0  # task: at most one request per second
INTERACTIVE_MAX_WAIT_S = 20.0
DAILY_RESERVE = 1500.0  # batch jobs leave this much of the daily budget for interactive requests
HOURLY_RESERVE = 1000.0  # ... and of the hourly one (one combined 1991-2050 request costs 939)


class QuotaExceeded(Exception):
    """The request would exceed a rate limit and waiting is not acceptable (interactive use)."""

    def __init__(self, scope: str, retry_after: float) -> None:
        super().__init__(f"Open-Meteo {scope} limit reached; retry in {retry_after:.0f} s")
        self.scope = scope
        self.retry_after = retry_after


def estimate_cost(n_series: int, n_days: int) -> float:
    """Estimated rate-limit cost of a request (validated against ``x-ratelimit-cost``)."""
    return n_series * n_days / COST_DIVISOR


def wait_needed(
    calls: Sequence[tuple[float, float]], now: float, window: float, limit: float, cost: float
) -> float:
    """Seconds until ``cost`` fits into ``limit`` within a rolling ``window``.

    ``calls`` are ``(timestamp, cost)`` pairs. Returns 0 when it fits now.
    """
    # A single request costing more than the whole limit is accepted by the server on an empty window
    # (measured 2026-11-04: cost 939.2 with a limit of 600 returned 200), so it needs a clear window.
    cost = min(cost, limit)
    recent = sorted((t, c) for t, c in calls if t > now - window)
    total = sum(c for _, c in recent)
    if total + cost <= limit:
        return 0.0
    for t, c in recent:
        total -= c
        if total + cost <= limit:
            return max(0.0, t + window - now)
    return window


@dataclass
class Fetched:
    """A successful response and what it cost."""

    data: dict[str, Any]
    cost: float
    elapsed_s: float


class OpenMeteoClient:
    """Throttled, quota-aware client; inject ``http``/``clock``/``sleep`` in tests."""

    def __init__(
        self,
        settings: OtpornoSettings,
        session_factory: sessionmaker[Session],
        *,
        http: httpx.Client | None = None,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        interactive: bool = False,
    ) -> None:
        self.settings = settings
        self._factory = session_factory
        self._own_http = http is None
        self.http = http or httpx.Client(
            timeout=httpx.Timeout(120.0, connect=10.0), headers={"User-Agent": user_agent(settings)}
        )
        self._clock = clock
        self._sleep = sleep
        self.interactive = interactive
        self._last_call = 0.0

    def close(self) -> None:
        """Close the HTTP client if this instance created it."""
        if self._own_http:
            self.http.close()

    # ------------------------------------------------------------------ budget
    def usage(self) -> list[tuple[float, float]]:
        """Calls of the last 24 h as ``(timestamp, cost)``."""
        since = datetime.fromtimestamp(self._clock(), UTC) - timedelta(days=1)
        with self._factory() as session:
            rows = session.execute(
                select(ApiCallLog.called_at, ApiCallLog.cost).where(
                    ApiCallLog.service == SERVICE, ApiCallLog.called_at > since
                )
            ).all()
        return [(r.called_at.timestamp(), float(r.cost)) for r in rows]

    def next_wait(self, cost: float, *, batch: bool) -> tuple[float, str]:
        """(seconds to wait, limiting scope) for a request of ``cost``."""
        now = self._clock()
        calls = self.usage()
        worst, scope = 0.0, "none"
        reserve = {"day": DAILY_RESERVE, "hour": HOURLY_RESERVE}
        for (window, limit), name in zip(LIMITS, ("minute", "hour", "day"), strict=True):
            cap = limit * SAFETY - (reserve.get(name, 0.0) if batch else 0.0)
            w = wait_needed(calls, now, window, cap, cost)
            if w > worst:
                worst, scope = w, name
        if (
            batch
        ):  # leave the minute window empty so an interactive passport can always run right after
            last = max((t for t, _ in calls), default=0.0)
            quiet = last + 60.0 - now
            if quiet > worst:
                worst, scope = quiet, "minute"
        return worst, scope

    def _log(self, cost: float, status: int, detail: str) -> None:
        with self._factory() as session:
            session.add(ApiCallLog(service=SERVICE, cost=cost, status=status, detail=detail[:300]))
            session.commit()

    # ------------------------------------------------------------------ requests
    def fetch(
        self,
        lat: float,
        lon: float,
        start: str,
        end: str,
        models: Sequence[str],
        daily: Sequence[str],
        *,
        batch: bool = False,
    ) -> Fetched:
        """One Climate API request, waiting (batch) or failing fast (interactive) when over budget."""
        n_days = (datetime.fromisoformat(end) - datetime.fromisoformat(start)).days + 1
        cost = estimate_cost(len(models) * len(daily), n_days)
        wait, scope = self.next_wait(cost, batch=batch)
        if wait > 0:
            if self.interactive and wait > INTERACTIVE_MAX_WAIT_S:
                raise QuotaExceeded(scope, wait)
            log.info("open_meteo_waiting", seconds=round(wait), scope=scope, cost=round(cost, 1))
            self._sleep(wait + 1.0)
        gap = MIN_INTERVAL_S - (self._clock() - self._last_call)
        if gap > 0:
            self._sleep(gap)
        params: dict[str, str | float] = {
            "latitude": lat,
            "longitude": lon,
            "start_date": start,
            "end_date": end,
            "models": ",".join(models),
            "daily": ",".join(daily),
            "timezone": "Europe/Zagreb",
        }
        detail = f"lat={lat} lon={lon} {start}..{end} models={len(models)} vars={len(daily)}"
        for attempt in range(3):
            self._last_call = self._clock()
            t0 = time.time()
            response = self.http.get(self.settings.open_meteo_climate_url, params=params)
            elapsed = time.time() - t0
            if response.status_code == 429:
                reason = _reason(response)
                self._log(0.0, 429, f"{reason} | {detail}")
                retry = _retry_seconds(reason)
                if self.interactive:
                    raise QuotaExceeded(_scope_of(reason), retry)
                log.warning("open_meteo_429", reason=reason, sleep_s=retry)
                self._sleep(retry)
                continue
            if response.status_code >= 500 and attempt < 2:
                self._sleep(5.0 * (attempt + 1))
                continue
            response.raise_for_status()
            real_cost = float(response.headers.get("x-ratelimit-cost", cost))
            self._log(real_cost, response.status_code, detail)
            log.info(
                "open_meteo_call",
                lat=lat,
                lon=lon,
                cost=round(real_cost, 1),
                seconds=round(elapsed, 2),
            )
            return Fetched(response.json(), real_cost, elapsed)
        raise QuotaExceeded("429", 60.0)


def _reason(response: httpx.Response) -> str:
    try:
        return str(response.json().get("reason", response.text))[:200]
    except ValueError:
        return response.text[:200]


def _scope_of(reason: str) -> str:
    """Which limit a 429 message talks about: minute, hour or day."""
    low = reason.lower()
    for key, scope in (("minutely", "minute"), ("hourly", "hour"), ("daily", "day")):
        if key in low:
            return scope
    return "unknown"


def _retry_seconds(reason: str) -> float:
    """Back-off after a 429: a minute for the minutely limit, longer for the hourly and daily ones."""
    return {"minute": 65.0, "hour": 3700.0, "day": 3600.0}.get(_scope_of(reason), 120.0)
