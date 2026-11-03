"""Planning: unmet need per cell and greedy placement of 1-5 new facilities."""

from __future__ import annotations

import threading
from collections import OrderedDict
from typing import Any

import numpy as np
import scipy.sparse as sp
from scipy.sparse.csgraph import dijkstra

from blizu_api.scoring import score
from blizu_api.store import DataStore
from opendata_core.optimize import greedy_mclp

THIN_M = 300.0
CHUNK = 128
CACHE_SIZE = 6


def thin_candidates(
    x: np.ndarray, y: np.ndarray, eligible: np.ndarray, cell_m: float = THIN_M
) -> np.ndarray:
    """One node per ``cell_m`` x ``cell_m`` square (the one nearest to the square's centre).

    ``eligible`` is a boolean mask of nodes that may become candidates. Returns node indices sorted
    ascending (deterministic).
    """
    idx = np.flatnonzero(eligible)
    if idx.size == 0:
        return idx
    gx = np.floor(x[idx] / cell_m).astype(np.int64)
    gy = np.floor(y[idx] / cell_m).astype(np.int64)
    cx = (gx + 0.5) * cell_m
    cy = (gy + 0.5) * cell_m
    d2 = (x[idx] - cx) ** 2 + (y[idx] - cy) ** 2
    order = np.lexsort((idx, d2, gy, gx))  # group by square, nearest to centre first, then index
    sg = np.stack([gx[order], gy[order]], axis=1)
    first = np.ones(len(order), dtype=bool)
    first[1:] = (sg[1:] != sg[:-1]).any(axis=1)
    return np.sort(idx[order][first])


def coverage_matrix(graph: sp.csr_matrix, candidates: np.ndarray, radius_m: float) -> sp.csr_matrix:
    """Boolean matrix (n_candidates x n_nodes): node reachable within ``radius_m`` network metres."""
    n = graph.shape[0]
    blocks = []
    for start in range(0, len(candidates), CHUNK):
        idx = candidates[start : start + CHUNK]
        dist = dijkstra(graph, directed=False, indices=idx, limit=radius_m)
        blocks.append(sp.csr_matrix(np.isfinite(dist)))
    if not blocks:
        return sp.csr_matrix((0, n), dtype=bool)
    return sp.vstack(blocks, format="csr")


class Planner:
    """Need maps and the facility-location optimiser on top of a :class:`DataStore`."""

    def __init__(self, store: DataStore) -> None:
        self.store = store
        graph = store.graph
        pop_total = np.nan_to_num(
            store.cells["pop_total"].to_numpy(dtype=float, na_value=np.nan), nan=0.0
        )
        in_cell = store.node_cell >= 0
        populated = np.zeros(graph.n_nodes, dtype=bool)
        populated[in_cell] = pop_total[store.node_cell[in_cell]] > 0
        self.candidates = thin_candidates(graph.x, graph.y, populated)
        self._cache: OrderedDict[tuple[str, int], sp.csr_matrix] = OrderedDict()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ shared node-level state
    def _node_state(self, category: str, persona: str) -> dict[str, Any]:
        """People, unmet-need demand and "already within g" per graph node.

        People of the target group are split equally over the nodes of their cell; demand is the
        cell's unmet need ``P * (1 - s(mean minutes))`` split the same way. A node counts as served
        when its network distance to the nearest facility is <= good_min * speed * 60 metres.
        Both ``need()`` and ``optimise()`` use this, so their shares are consistent.
        """
        store = self.store
        cat = store.cfg.categories[category]
        speed = store.cfg.personas[persona].speed_mps
        radius = cat.good_min * speed * 60.0
        pop, _column, label = store.group_population(category)
        minutes = store.cell_minutes(persona, category)
        s = np.array(
            [score(m, cat.good_min, cat.max_min) if np.isfinite(m) else 0.0 for m in minutes]
        )
        unmet_cell = pop * (1.0 - s)
        node_cell = store.node_cell
        valid = node_cell >= 0
        per_cell = np.where(store.nodes_per_cell > 0, store.nodes_per_cell, 1)
        people = np.zeros(store.graph.n_nodes)
        demand = np.zeros(store.graph.n_nodes)
        people[valid] = pop[node_cell[valid]] / per_cell[node_cell[valid]]
        demand[valid] = unmet_cell[node_cell[valid]] / per_cell[node_cell[valid]]
        dist, _fac = store.distance_array(persona, category)
        already = np.isfinite(dist) & (dist <= radius)
        return {
            "cat": cat,
            "radius": radius,
            "pop": pop,
            "label": label,
            "minutes": minutes,
            "unmet_cell": unmet_cell,
            "people": people,
            "demand": demand,
            "already": already,
        }

    # ------------------------------------------------------------------ need
    def need(self, category: str, persona: str) -> dict[str, Any]:
        """Unmet need per cell as a GeoJSON FeatureCollection plus a summary."""
        store = self.store
        state = self._node_state(category, persona)
        cat, pop, label = state["cat"], state["pop"], state["label"]
        minutes, unmet = state["minutes"], state["unmet_cell"]
        node_total = float(state["people"].sum())
        share_within = (
            float(state["people"][state["already"]].sum()) / node_total if node_total > 0 else None
        )
        total = float(pop.sum())
        positive = unmet[unmet > 0]
        breaks = (
            [float(v) for v in np.quantile(positive, [0.2, 0.4, 0.6, 0.8])]
            if positive.size >= 5
            else []
        )
        features = []
        for i, row in store.cells.iterrows():
            m = minutes[i]
            features.append(
                {
                    "type": "Feature",
                    "geometry": row["geometry"],
                    "properties": {
                        "grd_id": row["grd_id"],
                        "pop_group": round(float(pop[i]), 1),
                        "mean_minutes": None if not np.isfinite(m) else round(float(m), 1),
                        "unmet": round(float(unmet[i]), 1),
                    },
                }
            )
        return {
            "type": "FeatureCollection",
            "features": features,
            "summary": {
                "category": category,
                "persona": persona,
                "pop_group_label": label,
                "has_age_groups": store.has_age_groups,
                "pop_group_total": round(total),
                "share_within_g": share_within,
                "good_min": cat.good_min,
                "max_min": cat.max_min,
                "unmet_total": round(float(unmet.sum())),
                "breaks": breaks,
            },
        }

    # ------------------------------------------------------------------ optimiser
    def _coverage(self, variant: str, radius_m: float) -> sp.csr_matrix:
        key = (variant, int(round(radius_m)))
        with self._lock:
            hit = self._cache.get(key)
            if hit is not None:
                self._cache.move_to_end(key)
                return hit
        matrix = coverage_matrix(self.store.graph.variant(variant), self.candidates, radius_m)
        with self._lock:
            self._cache[key] = matrix
            while len(self._cache) > CACHE_SIZE:
                self._cache.popitem(last=False)
        return matrix

    def optimise(self, category: str, persona: str, k: int) -> dict[str, Any]:
        """Choose up to ``k`` sites maximising newly covered unmet need (greedy MCLP).

        Demand per node is its cell's unmet need split equally over the cell's nodes; a node is
        covered when a new site is within ``good_min`` walking minutes on the persona's graph. The
        reported figures are people of the target group (not weighted by unmet fraction).
        """
        store = self.store
        variant = store.cfg.personas[persona].graph
        state = self._node_state(category, persona)
        cat, radius, label = state["cat"], state["radius"], state["label"]
        people, demand, already = state["people"], state["demand"], state["already"]
        total_people = float(people.sum())
        before = float(people[already].sum())

        coverage = self._coverage(variant, radius)
        picks = greedy_mclp(demand, coverage, k, already_covered=already)

        covered = already.copy()
        sites = []
        newly_total = 0.0
        for cand_idx, _gain in picks:
            nodes = coverage.indices[coverage.indptr[cand_idx] : coverage.indptr[cand_idx + 1]]
            fresh = nodes[~covered[nodes]]
            newly = float(people[fresh].sum())
            covered[nodes] = True
            newly_total += newly
            node = int(self.candidates[cand_idx])
            sites.append(
                {
                    "lon": float(store.graph.lon[node]),
                    "lat": float(store.graph.lat[node]),
                    "street": store.street_near(node),
                    "newly_covered": int(round(newly)),
                }
            )
        denom = total_people if total_people > 0 else 1.0
        return {
            "category": category,
            "persona": persona,
            "k": k,
            "pop_group_label": label,
            "radius_m": round(radius),
            "good_min": cat.good_min,
            "sites": sites,
            "total_newly_covered": int(round(newly_total)),
            "share_before": before / denom,
            "share_after": (before + newly_total) / denom,
            "candidates": int(len(self.candidates)),
        }
