"""Planner building blocks on the REAL 1 km OSM subgraph."""

from __future__ import annotations

import numpy as np
import pytest
from scipy.sparse.csgraph import dijkstra

from blizu_api.ingest.graph import GraphData
from blizu_api.planner import coverage_matrix, thin_candidates


def test_thinning_gives_one_node_per_square(subgraph: GraphData) -> None:
    eligible = np.ones(subgraph.n_nodes, dtype=bool)
    cand = thin_candidates(subgraph.x, subgraph.y, eligible, 300.0)
    squares = {(int(subgraph.x[i] // 300), int(subgraph.y[i] // 300)) for i in cand}
    assert len(cand) == len(squares) > 5  # exactly one candidate per occupied 300 m square
    assert len(cand) < subgraph.n_nodes / 20
    assert (np.diff(cand) > 0).all()  # sorted, unique
    np.testing.assert_array_equal(cand, thin_candidates(subgraph.x, subgraph.y, eligible, 300.0))


def test_thinning_respects_eligibility(subgraph: GraphData) -> None:
    eligible = np.zeros(subgraph.n_nodes, dtype=bool)
    assert thin_candidates(subgraph.x, subgraph.y, eligible).size == 0
    eligible[:200] = True
    cand = thin_candidates(subgraph.x, subgraph.y, eligible)
    assert set(cand) <= set(range(200))


def test_candidate_is_nearest_to_square_centre(subgraph: GraphData) -> None:
    eligible = np.ones(subgraph.n_nodes, dtype=bool)
    cand = thin_candidates(subgraph.x, subgraph.y, eligible, 300.0)
    i = int(cand[0])
    gx, gy = int(subgraph.x[i] // 300), int(subgraph.y[i] // 300)
    members = np.flatnonzero((subgraph.x // 300 == gx) & (subgraph.y // 300 == gy))
    cx, cy = (gx + 0.5) * 300, (gy + 0.5) * 300
    d = np.hypot(subgraph.x[members] - cx, subgraph.y[members] - cy)
    assert i == members[np.argmin(d)]


@pytest.mark.parametrize("variant", ["full", "wheelchair"])
def test_coverage_matches_direct_dijkstra(subgraph: GraphData, variant: str) -> None:
    ones = np.ones(subgraph.n_nodes, dtype=bool)
    cand = thin_candidates(subgraph.x, subgraph.y, ones)[:12]
    radius = 600.0
    cov = coverage_matrix(subgraph.variant(variant), cand, radius)
    assert cov.shape == (12, subgraph.n_nodes)
    assert cov.dtype == bool
    direct = dijkstra(subgraph.variant(variant), directed=False, indices=cand)
    np.testing.assert_array_equal(cov.toarray(), direct <= radius)
    assert cov.toarray()[np.arange(12), cand].all()  # every candidate covers itself


def test_coverage_with_no_candidates(subgraph: GraphData) -> None:
    cov = coverage_matrix(subgraph.full, np.array([], dtype=int), 500.0)
    assert cov.shape == (0, subgraph.n_nodes)


def test_wheelchair_coverage_is_a_subset_of_full(subgraph: GraphData) -> None:
    ones = np.ones(subgraph.n_nodes, dtype=bool)
    cand = thin_candidates(subgraph.x, subgraph.y, ones)[:10]
    full = coverage_matrix(subgraph.full, cand, 700.0).toarray()
    wheel = coverage_matrix(subgraph.wheelchair, cand, 700.0).toarray()
    assert not (wheel & ~full).any()
    assert wheel.sum() < full.sum()


def test_parallel_and_serial_coverage_are_identical(subgraph: GraphData) -> None:
    ones = np.ones(subgraph.n_nodes, dtype=bool)
    cand = thin_candidates(subgraph.x, subgraph.y, ones)[:40]  # more than one chunk of 32
    serial = coverage_matrix(subgraph.full, cand, 650.0, workers=1)
    parallel = coverage_matrix(subgraph.full, cand, 650.0, workers=4)
    assert serial.shape == parallel.shape == (40, subgraph.n_nodes)
    assert (serial != parallel).nnz == 0
