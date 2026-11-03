"""Greedy solver for the maximum coverage location problem (MCLP)."""

from __future__ import annotations

import numpy as np
import scipy.sparse as sp
from numpy.typing import NDArray


def greedy_mclp(
    demand: NDArray[np.floating],
    coverage: sp.csr_matrix,
    k: int,
    already_covered: NDArray[np.bool_] | None = None,
) -> list[tuple[int, float]]:
    """Pick up to ``k`` candidates maximising newly covered demand, greedily.

    Args:
        demand: weight per demand point (length ``n_demand``, non-negative).
        coverage: boolean CSR matrix ``(n_candidates x n_demand)``; ``coverage[i, j]`` is True when
            candidate ``i`` covers demand point ``j``.
        k: maximum number of candidates to select.
        already_covered: demand points that are covered already (e.g. by existing facilities);
            they contribute no gain.

    Returns:
        ``[(candidate_index, newly_covered_demand), ...]`` in pick order. Ties are broken by the
        lowest candidate index (deterministic). Stops early when no candidate adds demand.
        Greedy guarantees at least ``1 - 1/e`` (~0.632) of the optimum.
    """
    n_cand, n_dem = coverage.shape
    demand = np.asarray(demand, dtype=float)
    if demand.shape != (n_dem,):
        raise ValueError(f"demand has shape {demand.shape}, expected ({n_dem},)")
    if (demand < 0).any():
        raise ValueError("demand must be non-negative")
    if k < 0:
        raise ValueError("k must be >= 0")
    covered = (
        np.zeros(n_dem, dtype=bool)
        if already_covered is None
        else np.asarray(already_covered, dtype=bool).copy()
    )
    if covered.shape != (n_dem,):
        raise ValueError("already_covered has the wrong length")

    cov = sp.csr_matrix(coverage, dtype=float)
    cov.eliminate_zeros()  # explicit False entries must not count as coverage
    picks: list[tuple[int, float]] = []
    for _ in range(min(k, n_cand)):
        gains = cov @ np.where(covered, 0.0, demand)
        best = int(np.argmax(gains))  # argmax returns the first maximum -> lowest index
        gain = float(gains[best])
        if gain <= 0.0:
            break
        picks.append((best, gain))
        covered[cov.indices[cov.indptr[best] : cov.indptr[best + 1]]] = True
    return picks
