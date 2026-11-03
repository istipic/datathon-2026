"""Resilient access to the public Overpass API (retry with exponential backoff, endpoint rotation).

The public servers regularly answer 429/502/504 when busy. osmnx caches every completed response
(``data/cache/osmnx``), so a retry only repeats the queries that failed.
"""

from __future__ import annotations

import time
from collections.abc import Callable

import structlog

log = structlog.get_logger(__name__)

ENDPOINTS = (
    "https://overpass-api.de/api",
    "https://overpass.kumi.systems/api",
    "https://overpass.private.coffee/api",
)
MAX_ATTEMPTS = 10
BASE_WAIT_S = 20.0
MAX_WAIT_S = 300.0

# Indirection so tests do not sleep.
_sleep = time.sleep


def backoff_seconds(attempt: int) -> float:
    """Wait before retry number ``attempt`` (1-based): 20, 40, 80, ... capped at 300 s."""
    return min(MAX_WAIT_S, BASE_WAIT_S * 2 ** (attempt - 1))


def with_overpass_retry[T](
    label: str,
    fn: Callable[[], T],
    set_endpoint: Callable[[str], None],
    endpoints: tuple[str, ...] = ENDPOINTS,
    max_attempts: int = MAX_ATTEMPTS,
) -> T:
    """Call ``fn`` until it succeeds, rotating endpoints and backing off between attempts."""
    last: Exception | None = None
    for attempt in range(1, max_attempts + 1):
        endpoint = endpoints[(attempt - 1) % len(endpoints)]
        set_endpoint(endpoint)
        try:
            return fn()
        except Exception as exc:
            last = exc
            wait = backoff_seconds(attempt)
            log.warning(
                "overpass_failed",
                label=label,
                attempt=attempt,
                endpoint=endpoint,
                error=str(exc)[:160].replace("\n", " "),
                retry_in_s=wait if attempt < max_attempts else None,
            )
            if attempt < max_attempts:
                _sleep(wait)
    raise RuntimeError(f"Overpass failed after {max_attempts} attempts ({label}): {last}") from last
