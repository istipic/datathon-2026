from __future__ import annotations

import itertools

import numpy as np
import pytest
import scipy.sparse as sp

from opendata_core.optimize import greedy_mclp


def _cov(rows: list[list[int]], n_dem: int) -> sp.csr_matrix:
    m = np.zeros((len(rows), n_dem), dtype=bool)
    for i, cols in enumerate(rows):
        m[i, cols] = True
    return sp.csr_matrix(m)


def test_hand_computed_example() -> None:
    # demand points 0..3 with weights 10, 5, 4, 3
    # candidates: c0 covers {0,1}=15, c1 covers {1,2}=9, c2 covers {2,3}=7
    demand = np.array([10.0, 5.0, 4.0, 3.0])
    cov = _cov([[0, 1], [1, 2], [2, 3]], 4)
    # k=1 -> c0 (15). k=2 -> c0, then c2 adds 4+3=7 (c1 would add only 4).
    assert greedy_mclp(demand, cov, 1) == [(0, 15.0)]
    assert greedy_mclp(demand, cov, 2) == [(0, 15.0), (2, 7.0)]
    # k=3: c1 would now add nothing -> greedy stops early
    assert greedy_mclp(demand, cov, 3) == [(0, 15.0), (2, 7.0)]


def test_already_covered_contributes_nothing() -> None:
    demand = np.array([10.0, 5.0, 4.0, 3.0])
    cov = _cov([[0, 1], [1, 2], [2, 3]], 4)
    covered = np.array([True, True, False, False])
    # c0 adds 0, c1 adds 4, c2 adds 7 -> c2 first; then c1 adds 0 (point 2 now covered)
    assert greedy_mclp(demand, cov, 3, already_covered=covered) == [(2, 7.0)]
    # the input mask must not be mutated
    assert covered.tolist() == [True, True, False, False]


def test_deterministic_lowest_index_tie_break() -> None:
    demand = np.array([1.0, 1.0])
    cov = _cov([[0], [1], [0], [1]], 2)  # all candidates tie at gain 1
    assert greedy_mclp(demand, cov, 2) == [(0, 1.0), (1, 1.0)]
    for _ in range(3):
        assert greedy_mclp(demand, cov, 2) == [(0, 1.0), (1, 1.0)]


def test_edge_cases() -> None:
    demand = np.array([1.0, 2.0])
    cov = _cov([[0], [1]], 2)
    assert greedy_mclp(demand, cov, 0) == []
    assert greedy_mclp(np.zeros(2), cov, 2) == []  # nothing to gain
    assert len(greedy_mclp(demand, cov, 10)) == 2  # k > candidates
    empty = sp.csr_matrix((0, 2), dtype=bool)
    assert greedy_mclp(demand, empty, 3) == []


def test_explicit_false_entries_do_not_count_as_coverage() -> None:
    demand = np.array([5.0, 1.0])
    m = sp.csr_matrix(np.array([[False, True]]))
    m = sp.csr_matrix(
        (np.array([False, True]), np.array([0, 1]), np.array([0, 2])), shape=(1, 2)
    )  # stores an explicit False at column 0
    assert greedy_mclp(demand, m, 1) == [(0, 1.0)]


def test_input_validation() -> None:
    cov = _cov([[0]], 2)
    with pytest.raises(ValueError, match="shape"):
        greedy_mclp(np.array([1.0]), cov, 1)
    with pytest.raises(ValueError, match="non-negative"):
        greedy_mclp(np.array([1.0, -1.0]), cov, 1)
    with pytest.raises(ValueError, match="k must"):
        greedy_mclp(np.array([1.0, 1.0]), cov, -1)
    with pytest.raises(ValueError, match="already_covered"):
        greedy_mclp(np.array([1.0, 1.0]), cov, 1, already_covered=np.array([True]))


def _optimum(demand: np.ndarray, cov: sp.csr_matrix, k: int) -> float:
    dense = cov.toarray()
    best = 0.0
    for combo in itertools.combinations(range(dense.shape[0]), min(k, dense.shape[0])):
        covered = dense[list(combo)].any(axis=0)
        best = max(best, float(demand[covered].sum()))
    return best


@pytest.mark.parametrize("seed", range(30))
def test_greedy_meets_approximation_bound_vs_brute_force(seed: int) -> None:
    rng = np.random.default_rng(seed)
    n_cand = int(rng.integers(4, 9))
    n_dem = int(rng.integers(6, 16))
    k = int(rng.integers(1, 4))  # k <= 3
    demand = rng.integers(1, 20, size=n_dem).astype(float)
    cov = sp.csr_matrix(rng.random((n_cand, n_dem)) < 0.35)
    picks = greedy_mclp(demand, cov, k)
    greedy_total = sum(gain for _, gain in picks)
    opt = _optimum(demand, cov, k)
    assert len(picks) <= k
    assert greedy_total <= opt + 1e-9
    assert greedy_total >= 0.632 * opt - 1e-9
    # reported gains must equal the real marginal coverage
    covered = np.zeros(n_dem, dtype=bool)
    for idx, gain in picks:
        row = cov[idx].toarray().ravel()
        assert gain == pytest.approx(float(demand[row & ~covered].sum()))
        covered |= row
