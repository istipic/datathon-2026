"""Cached ``/isochrone`` and ``/route`` responses (serialised once, served as bytes)."""

from __future__ import annotations

import json
from typing import Any

from blizu_api.isochrone import compute_isochrone
from blizu_api.route import compute_route
from blizu_api.store import DataStore
from blizu_api.walk import LruCache, WalkIndex, resolve_origin

ISOCHRONE_CACHE = 64  # each entry is a few hundred kB of JSON
ROUTE_CACHE = 256


def dumps(payload: dict[str, Any]) -> bytes:
    """Compact JSON (no NaN allowed)."""
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode()


class WalkService:
    """Validates, computes and caches; the HTTP layer only forwards the bytes.

    Keys: ``(lat5, lon5, persona, max_min)`` for isochrones and
    ``(lat5, lon5, persona, category, facility_id)`` for routes. Errors are not cached.
    """

    def __init__(self, store: DataStore) -> None:
        self.store = store
        self.index = WalkIndex(store)
        self._isochrones: LruCache[bytes] = LruCache(ISOCHRONE_CACHE)
        self._routes: LruCache[bytes] = LruCache(ROUTE_CACHE)

    def isochrone(self, lat: float, lon: float, persona: str, max_min: int) -> bytes:
        """JSON bytes of the isochrone payload."""
        origin = resolve_origin(self.store, lat, lon)
        key = (origin.lat, origin.lon, persona, max_min)
        return self._isochrones.get_or_compute(
            key,
            lambda: dumps(compute_isochrone(self.store, self.index, origin, persona, max_min)),
        )

    def route(
        self,
        lat: float,
        lon: float,
        persona: str,
        category: str | None = None,
        facility_id: int | None = None,
    ) -> bytes:
        """JSON bytes of the route payload."""
        origin = resolve_origin(self.store, lat, lon)
        key = (origin.lat, origin.lon, persona, category, facility_id)
        return self._routes.get_or_compute(
            key,
            lambda: dumps(
                compute_route(self.store, self.index, origin, persona, category, facility_id)
            ),
        )
