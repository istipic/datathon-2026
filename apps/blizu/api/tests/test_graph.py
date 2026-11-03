"""Graph building on a REAL 1 km OSM subgraph (3403 nodes, 8960 directed edges)."""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy.sparse.csgraph import dijkstra

from blizu_api.ingest.graph import (
    GraphData,
    graph_from_edges,
    is_wheelchair_blocked,
    load_graph,
    save_graph,
    undirected_csr,
)


@pytest.mark.parametrize(
    ("highway", "wheelchair", "blocked"),
    [
        ("steps", None, True),
        (["steps", "footway"], None, True),
        (["footway", "steps"], "yes", True),  # steps win even if tagged accessible
        ("footway", "no", True),
        ("footway", ["yes", "no"], True),
        ("footway", "yes", False),
        ("pedestrian", None, False),
        (None, None, False),
    ],
)
def test_wheelchair_blocking_rule(highway: object, wheelchair: object, blocked: bool) -> None:
    assert is_wheelchair_blocked(highway, wheelchair) is blocked


def test_undirected_csr_symmetric_min_weights_no_self_loops() -> None:
    u = np.array([0, 1, 0, 2])
    v = np.array([1, 0, 1, 2])  # 0-1 three times (two directions + parallel), 2-2 self loop
    w = np.array([10.0, 12.0, 7.0, 3.0])
    m = undirected_csr(u, v, w, 3)
    assert m[0, 1] == m[1, 0] == 7.0  # shortest parallel edge
    assert m[2, 2] == 0
    assert (m != m.T).nnz == 0


def test_subgraph_is_symmetric_and_metric(subgraph: GraphData) -> None:
    assert subgraph.n_nodes == 3403
    for m in (subgraph.full, subgraph.wheelchair):
        assert m.shape == (3403, 3403)
        assert (m != m.T).nnz == 0
        assert m.diagonal().sum() == 0
        assert (m.data > 0).all()
    # nodes were projected to HTRS96/TM: Zagreb centre has easting ~ 4.6e5, northing ~ 5.07e6
    assert 450_000 < subgraph.x.mean() < 470_000
    assert 5_060_000 < subgraph.y.mean() < 5_080_000


def test_edge_weights_are_lengths_in_metres(subgraph: GraphData, edges_frame: pd.DataFrame) -> None:
    longest = edges_frame["length"].max()
    assert subgraph.full.data.max() == pytest.approx(longest)
    # shortest recorded edge of the first row is present in the matrix
    row = edges_frame.iloc[0]
    index = {osm: i for i, osm in enumerate(subgraph.osmid)}
    a, b = index[row["u"]], index[row["v"]]
    if a != b:
        assert subgraph.full[a, b] <= row["length"] + 1e-6


def test_wheelchair_graph_drops_steps_only(subgraph: GraphData, edges_frame: pd.DataFrame) -> None:
    assert subgraph.wheelchair.nnz < subgraph.full.nnz  # the real box has hundreds of stepped edges
    index = {osm: i for i, osm in enumerate(subgraph.osmid)}
    blocked = edges_frame[
        [
            is_wheelchair_blocked(h, w)
            for h, w in zip(edges_frame["highway"], edges_frame["wheelchair"], strict=True)
        ]
    ]
    assert len(blocked) > 100
    # a blocked pair that has no unblocked parallel edge must be absent from the wheelchair graph
    ok = edges_frame.drop(blocked.index)
    ok_pairs = {frozenset((r.u, r.v)) for r in ok.itertuples()}
    checked = 0
    for r in blocked.itertuples():
        if frozenset((r.u, r.v)) in ok_pairs or r.u == r.v:
            continue
        assert subgraph.wheelchair[index[r.u], index[r.v]] == 0
        assert subgraph.full[index[r.u], index[r.v]] > 0
        checked += 1
    assert checked > 50


def test_wheelchair_distances_never_shorter_than_full(subgraph: GraphData) -> None:
    rng = np.random.default_rng(7)
    src = rng.choice(subgraph.n_nodes, size=15, replace=False)
    full = dijkstra(subgraph.full, directed=False, indices=src)
    wheel = dijkstra(subgraph.wheelchair, directed=False, indices=src)
    finite = np.isfinite(wheel)
    assert (wheel[finite] >= full[finite] - 1e-6).all()
    assert (wheel[finite] > full[finite] + 1).any()  # and sometimes strictly longer (detours)


def test_street_names_assigned(subgraph: GraphData) -> None:
    # only ~12 % of real OSM walking edges carry a name (sidewalks are separate footways)
    named = (subgraph.street != "").mean()
    assert 0.05 < named < 0.5
    assert "Tkalčićeva ulica" in set(subgraph.street)


def test_save_and_load_roundtrip(subgraph: GraphData, tmp_path: Path) -> None:
    path = tmp_path / "graph.npz"
    save_graph(subgraph, path)
    back = load_graph(path)
    assert back.n_nodes == subgraph.n_nodes
    np.testing.assert_array_equal(back.osmid, subgraph.osmid)
    np.testing.assert_allclose(back.x, subgraph.x)
    assert (back.full != subgraph.full).nnz == 0
    assert (back.wheelchair != subgraph.wheelchair).nnz == 0
    assert list(back.street[:50]) == list(subgraph.street[:50])


def test_graph_from_edges_without_optional_columns() -> None:
    nodes = np.array([1, 2, 3])
    edges = pd.DataFrame({"u": [1, 2], "v": [2, 3], "length": [100.0, 50.0]})
    g = graph_from_edges(
        nodes, np.array([15.97, 15.98, 15.99]), np.array([45.81, 45.81, 45.82]), edges
    )
    assert g.full.nnz == g.wheelchair.nnz == 4
    assert (g.street == "").all()
