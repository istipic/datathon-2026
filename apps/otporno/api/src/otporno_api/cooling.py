"""Proposed cooling-centre locations (maximum coverage of vulnerable residents).

Demand: 65+ residents of the municipality's cells in the heat bands *visoka* and *vrlo visoka*, split
equally over a 250 m point lattice inside each cell. Candidates: public OSM buildings. A candidate covers
a lattice point within a 415 m straight line (10 min at 0.9 m/s = 540 m, divided by a detour factor of
1.3). Selection with :func:`opendata_core.optimize.greedy_mclp`, k = 1-5.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import scipy.sparse as sp
from numpy.typing import NDArray
from pyproj import Transformer
from scipy.spatial import cKDTree
from sqlalchemy import text
from sqlalchemy.orm import Session

from opendata_core.geo import HTRS96_TM
from opendata_core.optimize import greedy_mclp
from otporno_api.constants import COOLING_RADIUS_M, LATTICE_M

_to_metric = Transformer.from_crs(4326, HTRS96_TM, always_xy=True)
HIGH_HEAT_PERCENTILE = 0.5  # band "visoka" starts at 0.5


@dataclass
class CoolingProblem:
    """Lattice demand points and candidate sites in metres (EPSG:3765)."""

    demand_xy: NDArray[np.float64]
    demand: NDArray[np.float64]
    sites_xy: NDArray[np.float64]
    sites: list[dict[str, Any]]


def lattice_in_cell(
    minx: float, miny: float, maxx: float, maxy: float, step: float = LATTICE_M
) -> NDArray[np.float64]:
    """Centres of the ``step`` m squares of a cell bounding box (4 x 4 = 16 points for a 1 km cell)."""
    nx = max(1, round((maxx - minx) / step))
    ny = max(1, round((maxy - miny) / step))
    xs = minx + (np.arange(nx) + 0.5) * (maxx - minx) / nx
    ys = miny + (np.arange(ny) + 0.5) * (maxy - miny) / ny
    gx, gy = np.meshgrid(xs, ys)
    return np.column_stack([gx.ravel(), gy.ravel()])


def load_problem(
    session: Session, lau_id: str, min_percentile: float = HIGH_HEAT_PERCENTILE
) -> CoolingProblem:
    """Demand lattice and candidates of a municipality from the database.

    Demand = 65+ residents of cells whose heat percentile is at least ``min_percentile`` (0.5 = band
    *visoka* and above, the default)."""
    cells = session.execute(
        text(
            """
            select c.grd_id, c.pop_65p, ST_XMin(ST_Transform(c.geom, 3765)) x0, ST_YMin(ST_Transform(c.geom, 3765)) y0,
                   ST_XMax(ST_Transform(c.geom, 3765)) x1, ST_YMax(ST_Transform(c.geom, 3765)) y1
            from cell c join heat_cell h using (grd_id)
            where c.lau_id = :lau and h.percentile >= :p and coalesce(c.pop_65p, 0) > 0
            """
        ),
        {"lau": lau_id, "p": min_percentile},
    ).all()
    pts, dem = [], []
    for c in cells:
        lat = lattice_in_cell(c.x0, c.y0, c.x1, c.y1)
        pts.append(lat)
        dem.append(np.full(len(lat), float(c.pop_65p) / len(lat)))
    demand_xy = np.vstack(pts) if pts else np.zeros((0, 2))
    demand = np.concatenate(dem) if dem else np.zeros(0)
    sites_rows = session.execute(
        text(
            "select id, name, kind, ST_X(geom) lon, ST_Y(geom) lat from candidate_site where lau_id = :lau order by id"
        ),
        {"lau": lau_id},
    ).all()
    sites = [
        {"id": r.id, "name": r.name, "kind": r.kind, "lon": r.lon, "lat": r.lat} for r in sites_rows
    ]
    if sites:
        x, y = _to_metric.transform([s["lon"] for s in sites], [s["lat"] for s in sites])
        sites_xy = np.column_stack([x, y])
    else:
        sites_xy = np.zeros((0, 2))
    return CoolingProblem(demand_xy, demand, sites_xy, sites)


def coverage_matrix(
    sites_xy: NDArray[np.float64], demand_xy: NDArray[np.float64], radius: float = COOLING_RADIUS_M
) -> sp.csr_matrix:
    """Boolean (n_sites x n_demand) matrix: demand point within ``radius`` metres (straight line) of a site."""
    n_s, n_d = len(sites_xy), len(demand_xy)
    if n_s == 0 or n_d == 0:
        return sp.csr_matrix((n_s, n_d), dtype=bool)
    tree = cKDTree(demand_xy)
    rows, cols = [], []
    for i, nb in enumerate(tree.query_ball_point(sites_xy, r=radius)):
        rows.extend([i] * len(nb))
        cols.extend(nb)
    return sp.csr_matrix((np.ones(len(rows), dtype=bool), (rows, cols)), shape=(n_s, n_d))


def propose(
    problem: CoolingProblem, k: int, *, covered_before_mask: NDArray[np.bool_] | None = None
) -> dict[str, Any]:
    """Choose up to ``k`` sites; returns the sites with the 65+ they newly cover, and the totals.

    ``covered_before`` is the demand already within reach of an existing cooling centre. No register of
    existing centres is available, so it is 0 unless a mask is given.
    """
    cov = coverage_matrix(problem.sites_xy, problem.demand_xy)
    already = (
        covered_before_mask
        if covered_before_mask is not None
        else np.zeros(len(problem.demand), dtype=bool)
    )
    before = float(problem.demand[already].sum())
    picks = (
        greedy_mclp(problem.demand, cov, k, already_covered=already)
        if len(problem.sites) and len(problem.demand)
        else []
    )
    covered = already.copy()
    out = []
    total_new = 0.0
    for idx, _gain in picks:
        nodes = cov.indices[cov.indptr[idx] : cov.indptr[idx + 1]]
        fresh = nodes[~covered[nodes]]
        newly = float(problem.demand[fresh].sum())
        covered[nodes] = True
        total_new += newly
        s = problem.sites[idx]
        out.append(
            {
                "id": s["id"],
                "name": s["name"],
                "kind": s["kind"],
                "lon": s["lon"],
                "lat": s["lat"],
                "newly_covered_65p": round(newly),
            }
        )
    return {
        "sites": out,
        "covered_before": round(before),
        "covered_after": round(before + total_new),
        "demand_total": round(float(problem.demand.sum())),
        "candidates": len(problem.sites),
        "radius_m": COOLING_RADIUS_M,
    }
