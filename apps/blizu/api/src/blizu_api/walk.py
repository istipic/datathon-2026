"""Shared building blocks of ``/isochrone`` and ``/route`` (free of FastAPI, unit-testable).

* :func:`resolve_origin` is the snapping and validation of ``/access`` (one implementation).
* :class:`WalkIndex` holds what both endpoints derive once from the store: the undirected edge list
  of each graph variant and, per category, the graph nodes through which each facility is reached.
  Facilities are snapped with the SAME function and distance as the ``/access`` arrays
  (``snap_facilities``: access points, <= 200 m), so a facility's walking time here equals the time
  ``/access`` reports when it is the nearest one.
* :class:`LruCache` is the small thread-safe cache of finished responses.
"""

from __future__ import annotations

import threading
from collections import OrderedDict
from collections.abc import Callable, Hashable
from dataclasses import dataclass

import numpy as np

from blizu_api import service
from blizu_api.ingest.access import snap_facilities
from blizu_api.store import DataStore

COORD_DECIMALS = 5  # ~1.1 m; also the cache-key resolution


class InvalidRequestError(ValueError):
    """The request parameters contradict each other (HTTP 422)."""


class NotReachableError(LookupError):
    """No such facility, or none within walking reach on the persona's graph (HTTP 404)."""


@dataclass(frozen=True)
class Origin:
    """A validated start point, rounded to :data:`COORD_DECIMALS`, and its graph node."""

    lat: float
    lon: float
    node: int
    snapped_m: float

    def as_json(self) -> dict[str, float]:
        """``{"lon", "lat", "snapped_m"}`` as exposed by the API."""
        return {"lon": self.lon, "lat": self.lat, "snapped_m": round(self.snapped_m, 1)}


def resolve_origin(store: DataStore, lat: float, lon: float) -> Origin:
    """Round to 5 decimals, then validate and snap exactly like ``/access``.

    Raises :class:`service.OutsideZagrebError` / :class:`service.FarFromNetworkError`.
    """
    lat, lon = round(lat, COORD_DECIMALS), round(lon, COORD_DECIMALS)
    node, snapped = service.resolve_origin(store, lat, lon)
    return Origin(lat=lat, lon=lon, node=node, snapped_m=snapped)


@dataclass(frozen=True)
class FacilityNodes:
    """Graph access points of one category (several per facility for parks)."""

    category: str
    nodes: np.ndarray  # graph node per access point
    owner: np.ndarray  # index into ``ids`` per access point
    ids: np.ndarray  # unique facility ids that have at least one access point, ascending
    lon: np.ndarray  # facility location per id
    lat: np.ndarray
    names: list[str]

    def per_facility_min(self, node_dist: np.ndarray) -> np.ndarray:
        """Smallest ``node_dist`` over the access points of each facility (``inf`` if none)."""
        best = np.full(len(self.ids), np.inf)
        np.minimum.at(best, self.owner, node_dist)
        return best


class WalkIndex:
    """Lazily built, read-only structures derived from a :class:`DataStore`."""

    def __init__(self, store: DataStore) -> None:
        self.store = store
        self._lock = threading.Lock()
        self._edges: dict[str, tuple[np.ndarray, np.ndarray]] = {}
        self._facilities: dict[str, FacilityNodes] = {}
        self.lon5 = np.round(store.graph.lon, COORD_DECIMALS)
        self.lat5 = np.round(store.graph.lat, COORD_DECIMALS)

    def edges(self, variant: str) -> tuple[np.ndarray, np.ndarray]:
        """Each undirected edge once: node index arrays ``(u, v)`` with ``u < v``."""
        with self._lock:
            hit = self._edges.get(variant)
            if hit is None:
                coo = self.store.graph.variant(variant).tocoo()
                keep = coo.row < coo.col
                hit = (coo.row[keep].astype(np.int64), coo.col[keep].astype(np.int64))
                self._edges[variant] = hit
            return hit

    def facilities(self, category: str) -> FacilityNodes:
        """Access points of a category (empty when the category has no data)."""
        with self._lock:
            hit = self._facilities.get(category)
            if hit is None:
                hit = self._build_facilities(category)
                self._facilities[category] = hit
            return hit

    def _build_facilities(self, category: str) -> FacilityNodes:
        store = self.store
        sub = store.facilities[store.facilities["category"] == category]
        if sub.empty:
            empty = np.empty(0, dtype=np.int64)
            return FacilityNodes(category, empty, empty, empty, np.empty(0), np.empty(0), [])
        snap = snap_facilities(sub, store.graph)
        ids, owner = np.unique(snap.facility_ids, return_inverse=True)
        rows = store.facilities.loc[ids]
        names = [service.display_name(store, category, _text(n)) for n in rows["name"].tolist()]
        return FacilityNodes(
            category=category,
            nodes=snap.nodes,
            owner=owner.astype(np.int64),
            ids=ids.astype(np.int64),
            lon=rows["lon"].to_numpy(dtype=float),
            lat=rows["lat"].to_numpy(dtype=float),
            names=names,
        )


def _text(value: object) -> str | None:
    """None for missing text (pandas NaN must never reach JSON)."""
    return value if isinstance(value, str) and value else None


class LruCache[T]:
    """Thread-safe least-recently-used cache."""

    def __init__(self, size: int) -> None:
        self.size = size
        self._data: OrderedDict[Hashable, T] = OrderedDict()
        self._lock = threading.Lock()

    def get_or_compute(self, key: Hashable, compute: Callable[[], T]) -> T:
        """Cached value of ``key``; ``compute()`` runs (outside the lock) on a miss."""
        with self._lock:
            if key in self._data:
                self._data.move_to_end(key)
                return self._data[key]
        value = compute()
        with self._lock:
            self._data[key] = value
            self._data.move_to_end(key)
            while len(self._data) > self.size:
                self._data.popitem(last=False)
        return value

    def __len__(self) -> int:
        return len(self._data)
