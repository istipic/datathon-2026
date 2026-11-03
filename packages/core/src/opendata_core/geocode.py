"""Nominatim (OpenStreetMap) geocoding — single, throttled, cached lookups only.

Usage policy (https://operations.osmfoundation.org/policies/nominatim/): max 1 request/second,
identifying User-Agent, cache results, no bulk geocoding. This module therefore offers only a
single-query ``search`` with a global 1 req/s throttle and a 30-day DB cache. DO NOT call it in
loops over datasets; use official coordinates or a local geocoder for bulk work.
"""

from __future__ import annotations

import re
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
from sqlalchemy import JSON, DateTime, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, Session, mapped_column

from opendata_core import http as http_mod
from opendata_core.config import CoreSettings
from opendata_core.db import Base

ATTRIBUTION = "© OpenStreetMap contributors (Nominatim)"
CACHE_TTL = timedelta(days=30)
MIN_INTERVAL_S = 1.0

_lock = threading.Lock()
_last_call = 0.0


class GeocodeCache(Base):
    """Cached Nominatim responses keyed by normalised query."""

    __tablename__ = "geocode_cache"

    q_norm: Mapped[str] = mapped_column(Text, primary_key=True)
    response: Mapped[Any] = mapped_column(JSON().with_variant(JSONB(), "postgresql"))
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


@dataclass(frozen=True)
class GeocodeResult:
    """Nominatim results plus provenance."""

    results: list[dict[str, Any]]
    attribution: str
    fetched_at: datetime
    from_cache: bool


def normalize_query(
    q: str, viewbox: tuple[float, float, float, float] | None = None, bounded: bool = False
) -> str:
    """Cache key: lower-cased, whitespace-collapsed query (+ viewbox/bounded when given)."""
    key = re.sub(r"\s+", " ", q.strip().lower())
    if viewbox is not None:
        key += "|vb=" + ",".join(f"{v:.5f}" for v in viewbox) + f"|b={int(bounded)}"
    return key


def _throttle() -> None:
    """Global 1 request/second limiter shared by all threads."""
    global _last_call
    with _lock:
        delay = _last_call + MIN_INTERVAL_S - time.monotonic()
        if delay > 0:
            time.sleep(delay)
        _last_call = time.monotonic()


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def search(
    session: Session,
    q: str,
    *,
    settings: CoreSettings,
    client: httpx.Client | None = None,
    viewbox: tuple[float, float, float, float] | None = None,
    bounded: bool = False,
) -> GeocodeResult:
    """Geocode one free-text query in Croatia.

    ``viewbox`` is ``(min_lon, min_lat, max_lon, max_lat)``; with ``bounded=True`` results are
    restricted to it. Returns cached results (flagged ``from_cache``, with their original
    ``fetched_at``) when younger than 30 days.
    """
    if not q.strip():
        raise ValueError("empty query")
    key = normalize_query(q, viewbox, bounded)
    now = datetime.now(UTC)
    cached = session.get(GeocodeCache, key)
    if cached is not None and now - _aware(cached.fetched_at) < CACHE_TTL:
        return GeocodeResult(list(cached.response), ATTRIBUTION, _aware(cached.fetched_at), True)

    params: dict[str, Any] = {
        "q": q,
        "format": "jsonv2",
        "countrycodes": "hr",
        "addressdetails": 1,
        "limit": 5,
        "accept-language": "hr",
    }
    if viewbox is not None:
        params["viewbox"] = ",".join(str(v) for v in viewbox)
        if bounded:
            params["bounded"] = 1
    own_client = client is None
    client = client or http_mod.make_client(settings)
    try:
        _throttle()
        results = http_mod.get_json(client, f"{settings.nominatim_url.rstrip('/')}/search", params)
    finally:
        if own_client:
            client.close()
    if not isinstance(results, list):
        raise ValueError("unexpected Nominatim response (expected a JSON array)")

    if cached is None:
        session.add(GeocodeCache(q_norm=key, response=results, fetched_at=now))
    else:
        cached.response = results
        cached.fetched_at = now
    session.commit()
    return GeocodeResult(results, ATTRIBUTION, now, False)
