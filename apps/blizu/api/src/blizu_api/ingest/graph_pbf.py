"""Walking graph from a Geofabrik extract (fallback when the public Overpass API is unavailable).

Reproduces ``osmnx.graph_from_place(..., network_type="walk", retain_all=False)`` closely:

- the same "walk" way filter (osmnx 2.x ``_get_network_filter``), including its regular-expression
  semantics (``highway!~"...motor..."`` excludes ``motorway`` too);
- ways are split into one edge per pair of consecutive nodes (no intersection simplification: it does
  not change shortest-path lengths); nodes outside the place polygon are dropped;
- only the largest connected component is kept.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any

import numpy as np
import osmium
import pandas as pd
import shapely
import structlog
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import connected_components
from shapely.geometry import box
from shapely.geometry.base import BaseGeometry

from blizu_api.ingest.graph import GraphData, graph_from_edges

log = structlog.get_logger(__name__)

EXCLUDED_HIGHWAY = re.compile(
    r"abandoned|bus_guideway|construction|cycleway|motor|no|planned|platform|proposed|raceway|razed|"
    r"rest_area|services"
)
SIDEWALK_KEYS = ("sidewalk", "sidewalk:both", "sidewalk:left", "sidewalk:right")
FALLBACK_BBOX = (15.70, 45.55, 16.30, 46.02)
EARTH_RADIUS_M = 6_371_008.8  # the radius osmnx uses for great-circle distances


def is_walkable(tags: dict[str, str]) -> bool:
    """osmnx 2.x "walk" filter: public, walkable ways (no area, cycleway, motorway, private, ...)."""
    highway = tags.get("highway")
    if not highway or EXCLUDED_HIGHWAY.search(highway):
        return False
    if tags.get("area") == "yes" or tags.get("access") == "private":
        return False
    if tags.get("foot") == "no" or tags.get("service") == "private":
        return False
    return all(tags.get(k) != "separate" for k in SIDEWALK_KEYS)


def haversine_m(
    lon1: np.ndarray, lat1: np.ndarray, lon2: np.ndarray, lat2: np.ndarray
) -> np.ndarray:
    """Great-circle distance in metres (vectorised)."""
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dphi, dlmb = p2 - p1, np.radians(lon2 - lon1)
    a = np.sin(dphi / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_M * np.arcsin(np.sqrt(a))


def read_walk_ways(
    pbf: Path, region: BaseGeometry | None
) -> tuple[pd.DataFrame, dict[int, tuple[float, float]]]:
    """Edges (one per consecutive node pair) of walkable ways touching the region, plus node coordinates.

    Returns ``(edges, coords)``; ``edges`` has ``u, v`` (OSM node ids), ``highway``, ``wheelchair``, ``name``.
    """
    min_lon, min_lat, max_lon, max_lat = region.bounds if region is not None else FALLBACK_BBOX
    bounds = box(min_lon, min_lat, max_lon, max_lat)
    fp = (
        osmium.FileProcessor(str(pbf))
        .with_locations()
        .with_filter(osmium.filter.KeyFilter("highway"))
    )
    u: list[int] = []
    v: list[int] = []
    attrs: list[tuple[str, str | None, str | None]] = []
    coords: dict[int, tuple[float, float]] = {}
    for obj in fp:
        if not obj.is_way():
            continue
        tags = {t.k: t.v for t in obj.tags}
        if not is_walkable(tags):
            continue
        nodes = [(n.ref, n.lon, n.lat) for n in obj.nodes if n.location.valid()]
        if len(nodes) < 2:
            continue
        probes = (nodes[0], nodes[len(nodes) // 2], nodes[-1])
        if not any(
            min_lon <= lon <= max_lon and min_lat <= lat <= max_lat for _, lon, lat in probes
        ):
            continue  # cheap bounding-box test before the exact one below
        info = (tags["highway"], tags.get("wheelchair"), tags.get("name"))
        for (a, alon, alat), (b, blon, blat) in zip(nodes, nodes[1:], strict=False):
            u.append(a)
            v.append(b)
            attrs.append(info)
            coords[a] = (alon, alat)
            coords[b] = (blon, blat)
    del bounds
    edges = pd.DataFrame(
        {
            "u": u,
            "v": v,
            "highway": [a[0] for a in attrs],
            "wheelchair": [a[1] for a in attrs],
            "name": [a[2] for a in attrs],
        }
    )
    return edges, coords


def graph_from_extract(pbf: Path, region: BaseGeometry | None) -> GraphData:
    """Build the two-variant walking graph of ``region`` (the place polygon) from an OSM PBF extract."""
    edges, coords = read_walk_ways(pbf, region)
    if edges.empty:
        raise ValueError("no walkable ways found in the extract for the region")
    ids = np.fromiter(coords.keys(), dtype=np.int64, count=len(coords))
    lonlat = np.array([coords[int(i)] for i in ids])
    inside = (
        shapely.contains_xy(region, lonlat[:, 0], lonlat[:, 1])
        if region is not None
        else np.ones(len(ids), dtype=bool)
    )
    keep_ids = set(ids[inside].tolist())
    edges = edges[
        edges["u"].isin(keep_ids) & edges["v"].isin(keep_ids) & (edges["u"] != edges["v"])
    ]
    index = pd.Series(np.arange(len(ids)), index=ids)
    ui, vi = index.loc[edges["u"]].to_numpy(), index.loc[edges["v"]].to_numpy()
    lon, lat = lonlat[:, 0], lonlat[:, 1]
    edges = edges.assign(length=haversine_m(lon[ui], lat[ui], lon[vi], lat[vi]))

    # largest connected component only (osmnx retain_all=False)
    n = len(ids)
    adj = coo_matrix((np.ones(len(ui)), (ui, vi)), shape=(n, n))
    _, labels = connected_components(adj, directed=False)
    biggest = np.bincount(labels[np.unique(np.concatenate([ui, vi]))]).argmax()
    in_lcc = labels == biggest
    edges = edges[in_lcc[ui] & in_lcc[vi]]
    node_ids = ids[in_lcc]
    log.info("graph_from_extract", nodes=int(in_lcc.sum()), edges=len(edges), pbf=pbf.name)
    return graph_from_edges(node_ids, lon[in_lcc], lat[in_lcc], edges.reset_index(drop=True))


def region_or_box(boundary: Any | None) -> BaseGeometry:
    """The place polygon, or a Zagreb box when the boundary could not be fetched."""
    return boundary if boundary is not None else box(*FALLBACK_BBOX)
