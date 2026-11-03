"""CRS constants and small geometry helpers (WGS84 <-> HTRS96/TM, bbox, KD-tree snapping)."""

from __future__ import annotations

import math
from collections.abc import Iterable

import geopandas as gpd
import numpy as np
from numpy.typing import NDArray
from pyproj import Geod
from scipy.spatial import cKDTree

WGS84 = 4326
HTRS96_TM = 3765

# Rough bounding box of Croatia (lon 13.0-19.5, lat 42.2-46.6).
CROATIA_BBOX = (13.0, 42.2, 19.5, 46.6)  # (min_lon, min_lat, max_lon, max_lat)

_GEOD = Geod(ellps="WGS84")


def to_metric(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Reproject to HTRS96/TM (EPSG:3765, metres). The input must have a CRS."""
    if gdf.crs is None:
        raise ValueError("GeoDataFrame has no CRS; set it explicitly before projecting")
    return gdf.to_crs(HTRS96_TM)


def in_croatia(lon: float, lat: float) -> bool:
    """True if the WGS84 point is inside Croatia's rough bounding box."""
    min_lon, min_lat, max_lon, max_lat = CROATIA_BBOX
    return min_lon <= lon <= max_lon and min_lat <= lat <= max_lat


def bbox_of_points(points: Iterable[tuple[float, float]]) -> tuple[float, float, float, float]:
    """``(min_lon, min_lat, max_lon, max_lat)`` of ``(lon, lat)`` points."""
    arr = np.asarray(list(points), dtype=float)
    if arr.size == 0:
        raise ValueError("no points")
    return (
        float(arr[:, 0].min()),
        float(arr[:, 1].min()),
        float(arr[:, 0].max()),
        float(arr[:, 1].max()),
    )


def bbox_around(lon: float, lat: float, radius_m: float) -> tuple[float, float, float, float]:
    """Bounding box (WGS84) of the square circumscribing a circle of ``radius_m`` metres."""
    if radius_m < 0:
        raise ValueError("radius_m must be >= 0")
    east, _, _ = _GEOD.fwd(lon, lat, 90, radius_m)
    west, _, _ = _GEOD.fwd(lon, lat, 270, radius_m)
    _, north, _ = _GEOD.fwd(lon, lat, 0, radius_m)
    _, south, _ = _GEOD.fwd(lon, lat, 180, radius_m)
    return (float(west), float(south), float(east), float(north))


def bbox_contains(bbox: tuple[float, float, float, float], lon: float, lat: float) -> bool:
    """True if ``(lon, lat)`` lies inside ``bbox`` (inclusive)."""
    return bbox[0] <= lon <= bbox[2] and bbox[1] <= lat <= bbox[3]


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Geodesic distance in metres between two WGS84 points."""
    _, _, dist = _GEOD.inv(lon1, lat1, lon2, lat2)
    return float(dist)


def snap_points_to_nodes(
    points_xy: NDArray[np.floating],
    nodes_xy: NDArray[np.floating],
    max_dist_m: float,
) -> tuple[NDArray[np.int64], NDArray[np.float64]]:
    """Snap each point to its nearest node (coordinates in a metric CRS).

    Returns ``(indices, distances)``; ``indices[i] == -1`` and ``distances[i] == inf`` when the
    nearest node is farther than ``max_dist_m`` (or there are no nodes).
    """
    pts = np.asarray(points_xy, dtype=float).reshape(-1, 2)
    nodes = np.asarray(nodes_xy, dtype=float).reshape(-1, 2)
    if len(nodes) == 0 or len(pts) == 0:
        return (
            np.full(len(pts), -1, dtype=np.int64),
            np.full(len(pts), math.inf, dtype=np.float64),
        )
    tree = cKDTree(nodes)
    # cKDTree's bound is exclusive; nextafter makes "exactly max_dist_m" still snap.
    dist, idx = tree.query(pts, k=1, distance_upper_bound=float(np.nextafter(max_dist_m, np.inf)))
    idx = np.asarray(idx, dtype=np.int64)
    dist = np.asarray(dist, dtype=np.float64)
    missing = ~np.isfinite(dist)  # cKDTree returns inf / index n for "no neighbour"
    idx[missing] = -1
    dist[missing] = math.inf
    return idx, dist
