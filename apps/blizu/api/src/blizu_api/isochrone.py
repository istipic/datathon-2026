"""``GET /isochrone``: the walkable streets grouped by walking-time bucket (free of FastAPI).

One Dijkstra from the snapped origin on the persona's graph variant. Time of a node is
``(snap distance + network distance) / speed``, i.e. the origin's snap distance is included exactly
like in ``/access`` (``total_m = snapped + d``), so the flood front and the facility minutes agree
with the minutes of ``/access``.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.sparse.csgraph import dijkstra

from blizu_api.constants import CATEGORIES
from blizu_api.scoring import minutes
from blizu_api.store import DataStore
from blizu_api.walk import Origin, WalkIndex

BUCKET_MIN = 0.25  # minutes per bucket: 20 min -> at most 80 features
MIN_MAX_MIN = 5
MAX_MAX_MIN = 20
COUNT_THRESHOLDS = (5, 10, 15, 20)  # cumulative counts per category, those <= max_min


def build_buckets(
    index: WalkIndex,
    variant: str,
    dist: np.ndarray,
    snapped_m: float,
    speed_mps: float,
    max_min: int,
) -> list[dict[str, Any]]:
    """GeoJSON features, one MultiLineString per time bucket (ascending ``t``).

    An edge (u, v) with both ends reached belongs to bucket ``ceil(min(t_u, t_v) / 0.25) * 0.25``
    and is drawn as the straight segment between its nodes. Edges whose far end lies beyond the
    limit (distance ``inf``) are dropped. The first bucket index is 1 (an edge touching the origin
    at time 0 goes to ``t = 0.25``), so there are at most ``4 * max_min`` buckets.
    """
    eu, ev = index.edges(variant)
    du, dv = dist[eu], dist[ev]
    keep = np.isfinite(du) & np.isfinite(dv)
    if not keep.any():
        return []
    u, v = eu[keep], ev[keep]
    near = np.minimum(du[keep], dv[keep])
    t = (snapped_m + near) / (speed_mps * 60.0)
    k = np.ceil(t / BUCKET_MIN - 1e-9).astype(np.int64)
    k = np.clip(k, 1, int(max_min / BUCKET_MIN))
    order = np.argsort(k, kind="stable")
    k, u, v = k[order], u[order], v[order]
    starts = np.flatnonzero(np.r_[True, k[1:] != k[:-1]])
    ends = np.r_[starts[1:], len(k)]
    features: list[dict[str, Any]] = []
    for s, e in zip(starts.tolist(), ends.tolist(), strict=True):
        seg = np.stack(
            [
                np.column_stack([index.lon5[u[s:e]], index.lat5[u[s:e]]]),
                np.column_stack([index.lon5[v[s:e]], index.lat5[v[s:e]]]),
            ],
            axis=1,
        )  # (edges, 2 points, 2 coords)
        features.append(
            {
                "type": "Feature",
                "properties": {"t": float(k[s] * BUCKET_MIN)},
                "geometry": {"type": "MultiLineString", "coordinates": seg.tolist()},
            }
        )
    return features


def reachable_facilities(
    store: DataStore,
    index: WalkIndex,
    dist: np.ndarray,
    snapped_m: float,
    speed_mps: float,
    max_min: int,
) -> list[dict[str, Any]]:
    """Facilities of every category within ``max_min`` walking minutes, nearest first.

    ``t`` is rounded to one decimal like ``minutes`` in ``/access``; a facility reached through
    several access points (parks) uses the nearest one.
    """
    out: list[dict[str, Any]] = []
    limit_m = max_min * 60.0 * speed_mps
    for category in CATEGORIES:
        fn = index.facilities(category)
        if not len(fn.ids):
            continue
        total = snapped_m + fn.per_facility_min(dist[fn.nodes])
        for i in np.flatnonzero(total <= limit_m).tolist():
            out.append(
                {
                    "id": int(fn.ids[i]),
                    "category": category,
                    "name": fn.names[i],
                    "t": round(minutes(float(total[i]), speed_mps), 1),
                    "lon": float(fn.lon[i]),
                    "lat": float(fn.lat[i]),
                }
            )
    out.sort(key=lambda f: (f["t"], f["category"], f["id"]))
    return out


def count_by_threshold(facilities: list[dict[str, Any]], max_min: int) -> dict[str, dict[str, int]]:
    """Cumulative number of facilities per category within 5 / 10 / 15 / 20 minutes (<= max_min).

    Categories with no facility in reach are left out (``"15": {}`` means nothing in reach).
    """
    counts: dict[str, dict[str, int]] = {}
    for threshold in COUNT_THRESHOLDS:
        if threshold > max_min:
            continue
        per_category: dict[str, int] = {}
        for f in facilities:
            if f["t"] <= threshold:
                per_category[f["category"]] = per_category.get(f["category"], 0) + 1
        counts[str(threshold)] = per_category
    return counts


def compute_isochrone(
    store: DataStore, index: WalkIndex, origin: Origin, persona: str, max_min: int
) -> dict[str, Any]:
    """The ``/isochrone`` payload for a validated origin."""
    persona_cfg = store.cfg.personas[persona]
    speed = persona_cfg.speed_mps
    limit_total_m = max_min * 60.0 * speed
    variant = persona_cfg.graph
    if origin.snapped_m > limit_total_m:  # the snap distance alone uses up the time budget
        dist = np.full(store.graph.n_nodes, np.inf)
    else:
        dist = dijkstra(
            store.graph.variant(variant),
            directed=True,  # the CSR matrices are symmetric (see undirected_csr)
            indices=origin.node,
            limit=limit_total_m - origin.snapped_m,
        )
    facilities = reachable_facilities(store, index, dist, origin.snapped_m, speed, max_min)
    return {
        "origin": origin.as_json(),
        "persona": persona,
        "speed_mps": speed,
        "max_min": max_min,
        "bucket_min": BUCKET_MIN,
        "buckets": {
            "type": "FeatureCollection",
            "features": build_buckets(index, variant, dist, origin.snapped_m, speed, max_min),
        },
        "facilities": facilities,
        "counts": count_by_threshold(facilities, max_min),
    }
