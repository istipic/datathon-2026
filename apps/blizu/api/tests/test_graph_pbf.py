"""Walking graph from a Geofabrik extract (fallback route) - filter rules and a real-extract build."""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pytest
from scipy.sparse.csgraph import connected_components, dijkstra
from shapely.geometry import shape
from shapely.ops import unary_union

from blizu_api.ingest import graph_pbf as gp

ROOT = Path(__file__).parents[2] / "data"
REAL_EXTRACT = ROOT / "raw" / "2026-11-03_croatia-latest.osm.pbf"
BOUNDARY = ROOT / "derived" / "zagreb-boundary_2026-11-03.geojson"
OSMNX_GRAPH = ROOT / "derived" / "graph_2026-11-03.npz"


@pytest.mark.parametrize(
    ("tags", "walkable"),
    [
        ({"highway": "footway"}, True),
        ({"highway": "residential"}, True),
        ({"highway": "steps"}, True),  # kept; only the wheelchair graph drops steps
        ({"highway": "pedestrian"}, True),
        ({"highway": "service"}, True),
        ({"highway": "path", "foot": "yes"}, True),
        ({"highway": "motorway"}, False),  # osmnx regex "motor" also matches motorway
        ({"highway": "motorway_link"}, False),
        ({"highway": "cycleway"}, False),
        ({"highway": "construction"}, False),
        ({"highway": "proposed"}, False),
        ({"highway": "platform"}, False),
        ({"highway": "footway", "foot": "no"}, False),
        ({"highway": "service", "service": "private"}, False),
        ({"highway": "residential", "access": "private"}, False),
        ({"highway": "pedestrian", "area": "yes"}, False),
        ({"highway": "residential", "sidewalk": "separate"}, False),
        ({"highway": "residential", "sidewalk:left": "separate"}, False),
        ({"highway": "residential", "sidewalk": "both"}, True),
        ({}, False),
        ({"building": "yes"}, False),
    ],
)
def test_walk_filter_matches_osmnx(tags: dict[str, str], walkable: bool) -> None:
    assert gp.is_walkable(tags) is walkable


def test_haversine_known_distance() -> None:
    # Trg bana Jelacica -> Glavni kolodvor is roughly 1.0 km
    d = gp.haversine_m(
        np.array([15.9771683]), np.array([45.8130887]), np.array([15.9815]), np.array([45.8045])
    )[0]
    assert 900 < d < 1100
    assert (
        gp.haversine_m(np.array([16.0]), np.array([45.0]), np.array([16.0]), np.array([45.0]))[0]
        == 0
    )


@pytest.mark.skipif(
    not (REAL_EXTRACT.exists() and BOUNDARY.exists()),
    reason="real extract / boundary not downloaded",
)
def test_graph_from_the_real_extract_is_a_connected_symmetric_zagreb_graph() -> None:
    region = unary_union(
        [shape(f["geometry"]) for f in json.loads(BOUNDARY.read_text(encoding="utf-8"))["features"]]
    )
    g = gp.graph_from_extract(REAL_EXTRACT, region)
    assert 150_000 < g.n_nodes < 800_000
    for m in (g.full, g.wheelchair):
        assert (m != m.T).nnz == 0
        assert m.diagonal().sum() == 0
        assert (m.data > 0).all()
    # one connected component (retain_all=False), a bit fewer edges for wheelchairs
    n_comp, _ = connected_components(g.full, directed=False)
    nodes_with_edges = np.flatnonzero(np.diff(g.full.indptr) > 0)
    assert len(nodes_with_edges) == g.n_nodes  # no isolated nodes survive
    assert n_comp == 1
    assert g.wheelchair.nnz < g.full.nnz
    assert region.contains(shape({"type": "Point", "coordinates": [g.lon[0], g.lat[0]]}))
    assert g.lon.min() > 15.77
    assert g.lon.max() < 16.24
    assert g.lat.min() > 45.61
    assert g.lat.max() < 45.97
    assert "Tkalčićeva ulica" in set(g.street)
    assert (
        6000 < g.full.data.sum() / 2000 < 7500
    )  # total network length in km (Zagreb ~ 6.6-6.8 thousand)


@pytest.mark.skipif(
    not (REAL_EXTRACT.exists() and BOUNDARY.exists() and OSMNX_GRAPH.exists()),
    reason="real extract / osmnx graph not available",
)
def test_extract_graph_gives_the_same_network_distances_as_the_osmnx_graph() -> None:
    from pyproj import Transformer
    from scipy.spatial import cKDTree

    from blizu_api.ingest.graph import load_graph

    region = unary_union(
        [shape(f["geometry"]) for f in json.loads(BOUNDARY.read_text(encoding="utf-8"))["features"]]
    )
    g = gp.graph_from_extract(REAL_EXTRACT, region)
    o = load_graph(OSMNX_GRAPH)
    tr = Transformer.from_crs(4326, 3765, always_xy=True)

    def snap(graph, lon, lat):  # type: ignore[no-untyped-def]
        x, y = tr.transform(lon, lat)
        return cKDTree(np.column_stack([graph.x, graph.y])).query(np.column_stack([x, y]))[1]

    rng = np.random.default_rng(3)
    a = rng.choice(o.n_nodes, 40, replace=False)
    b = rng.choice(o.n_nodes, 40, replace=False)
    ao, bo = snap(o, o.lon[a], o.lat[a]), snap(o, o.lon[b], o.lat[b])
    ag, bg = snap(g, o.lon[a], o.lat[a]), snap(g, o.lon[b], o.lat[b])
    ratios = []
    for k in range(40):
        do = dijkstra(o.full, directed=False, indices=ao[k])[bo[k]]
        dg = dijkstra(g.full, directed=False, indices=ag[k])[bg[k]]
        if np.isfinite(do) and np.isfinite(dg) and do > 300:
            ratios.append(dg / do)
    assert len(ratios) >= 30
    assert np.median(ratios) == pytest.approx(1.0, abs=0.02)
    assert np.percentile(ratios, 10) > 0.9
    assert np.percentile(ratios, 90) < 1.1
