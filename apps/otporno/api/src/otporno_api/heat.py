"""Heat indicators: Open-Meteo points (national grid + addresses), ensemble statistics, percentile, cells.

Quota (docs/adr/0007): a full point (3 models, Tmax+Tmin, 1991-2020 and 2031-2050) costs about 780 of
the 10 000 daily calls, a grid point (3 models, Tmax, 2031-2050) about 157. The national 0.25 degree grid
therefore fills over several days; its points are visited farthest-first so that every prefix is a
spatially even sample and the percentile is meaningful early on (the number of grid points used is
always reported).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any

import structlog
from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from otporno_api.constants import BAND_EDGES, BANDS, MODELS
from otporno_api.db import HeatCell, HeatPoint
from otporno_api.heat_calc import all_models, ensemble
from otporno_api.om_client import OpenMeteoClient

log = structlog.get_logger(__name__)

BASE_WINDOW = ("1991-01-01", "2020-12-31")
FUT_WINDOW = ("2031-01-01", "2050-12-31")
VARS_FULL = ("temperature_2m_max", "temperature_2m_min")
VARS_GRID = ("temperature_2m_max",)
GRID_STEP = 0.25
APPROX_MAX_KM = 25.0  # nearest fetched point used for a cell without its own 0.1 degree point


def round_coord(value: float) -> float:
    """Round to 0.1 degree (and avoid ``-0.0``)."""
    return round(value, 1) + 0.0


def band_of(score: float | None) -> str | None:
    """Band of a 0-1 score: niska < 0.25 <= umjerena < 0.5 <= visoka < 0.8 <= vrlo visoka."""
    if score is None:
        return None
    for edge, band in zip(BAND_EDGES, BANDS, strict=False):
        if score < edge:
            return band
    return BANDS[-1]


def km_between(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Equirectangular distance in km (good enough at these scales)."""
    x = math.radians(lon2 - lon1) * math.cos(math.radians((lat1 + lat2) / 2))
    y = math.radians(lat2 - lat1)
    return 6371.0 * math.hypot(x, y)


def farthest_first(points: Sequence[tuple[float, float]]) -> list[tuple[float, float]]:
    """Order points so that every prefix is spread out (greedy farthest-point sampling)."""
    if not points:
        return []
    cy = sum(p[0] for p in points) / len(points)
    cx = sum(p[1] for p in points) / len(points)
    remaining = list(points)
    first = min(remaining, key=lambda p: km_between(p[0], p[1], cy, cx))
    order = [first]
    remaining.remove(first)
    nearest = {p: km_between(p[0], p[1], first[0], first[1]) for p in remaining}
    while remaining:
        nxt = max(remaining, key=lambda p: nearest[p])
        order.append(nxt)
        remaining.remove(nxt)
        for p in remaining:
            nearest[p] = min(nearest[p], km_between(p[0], p[1], nxt[0], nxt[1]))
    return order


# ---------------------------------------------------------------------------- points


def grid_lattice(session: Session) -> list[tuple[float, float]]:
    """0.25 degree lattice points inside Croatia (inside a municipality polygon), farthest-first."""
    rows = session.execute(
        text(
            """
            select lat, lon from (
                select (la * 0.25)::float as lat, (lo * 0.25)::float as lon
                from generate_series(168, 188) la, generate_series(53, 79) lo
            ) g
            where exists (
                select 1 from municipality m
                where ST_Intersects(m.geom, ST_SetSRID(ST_MakePoint(g.lon, g.lat), 4326))
            )
            """
        )
    ).all()
    return farthest_first([(float(r.lat), float(r.lon)) for r in rows])


def demo_points(session: Session, lau_id: str) -> list[tuple[float, float]]:
    """Distinct 0.1 degree points of the inhabited cells of a municipality (the heat points it needs)."""
    rows = session.execute(
        text(
            """
            select distinct round(ST_Y(centroid)::numeric, 1) as lat, round(ST_X(centroid)::numeric, 1) as lon
            from cell where lau_id = :lau and coalesce(pop_total, 0) > 0
            """
        ),
        {"lau": lau_id},
    ).all()
    return sorted((float(r.lat), float(r.lon)) for r in rows)


def stored_models(session: Session, lat: float, lon: float, *, full: bool) -> set[str]:
    """Models that already have a (full, or any) row for this point."""
    q = select(HeatPoint.model).where(
        HeatPoint.lat_r == round(lat, 3), HeatPoint.lon_r == round(lon, 3)
    )
    if full:
        q = q.where(HeatPoint.base_hot_days.is_not(None), HeatPoint.fut_trop_nights.is_not(None))
    else:
        q = q.where(HeatPoint.fut_hot_days.is_not(None))
    return set(session.scalars(q))


def _upsert(session: Session, rows: list[dict[str, Any]]) -> None:
    stmt = insert(HeatPoint).values(rows)
    keep = {"lat_r", "lon_r", "model"}
    update: dict[str, Any] = {c: getattr(stmt.excluded, c) for c in rows[0] if c not in keep}
    update["fetched_at"] = text("now()")
    session.execute(
        stmt.on_conflict_do_update(index_elements=["lat_r", "lon_r", "model"], set_=update)
    )
    session.commit()


def fetch_full_point(
    client: OpenMeteoClient,
    session: Session,
    lat: float,
    lon: float,
    *,
    batch: bool,
    combined: bool = False,
) -> list[str]:
    """Base and future hot days / tropical nights of the three models at one 0.1 degree point.

    ``combined`` uses one request for 1991-2050 (cost 939, used by interactive callers so the cold path
    is a single round trip); otherwise two requests (base, future) cost 783 in total.
    """
    if combined:
        both = client.fetch(
            lat, lon, BASE_WINDOW[0], FUT_WINDOW[1], MODELS, VARS_FULL, batch=batch
        ).data["daily"]
        base_m = fut_m = all_models(both)
    else:
        base = client.fetch(lat, lon, *BASE_WINDOW, MODELS, VARS_FULL, batch=batch).data["daily"]
        fut = client.fetch(lat, lon, *FUT_WINDOW, MODELS, VARS_FULL, batch=batch).data["daily"]
        base_m, fut_m = all_models(base), all_models(fut)
    rows = []
    for model in MODELS:
        b, f = base_m.get(model), fut_m.get(model)
        if not b or not f:
            continue
        rows.append(
            {
                "lat_r": round(lat, 3),
                "lon_r": round(lon, 3),
                "model": model,
                "base_hot_days": b["base_hot_days"],
                "fut_hot_days": f["fut_hot_days"],
                "base_trop_nights": b["base_trop_nights"],
                "fut_trop_nights": f["fut_trop_nights"],
                "kind": "address",
            }
        )
    if rows:
        _upsert(session, rows)
    return [str(r["model"]) for r in rows]


def fetch_grid_point(
    client: OpenMeteoClient, session: Session, lat: float, lon: float, *, batch: bool
) -> list[str]:
    """Future hot days only (the percentile reference): cheaper than a full point."""
    fut = client.fetch(lat, lon, *FUT_WINDOW, MODELS, VARS_GRID, batch=batch).data["daily"]
    metrics = all_models(fut)
    rows = [
        {
            "lat_r": round(lat, 3),
            "lon_r": round(lon, 3),
            "model": m,
            "fut_hot_days": v["fut_hot_days"],
            "kind": "grid",
        }
        for m, v in metrics.items()
    ]
    if rows:
        _upsert(session, rows)
    return [str(r["model"]) for r in rows]


# ---------------------------------------------------------------------------- statistics


@dataclass(frozen=True)
class PointStats:
    """Ensemble statistics of one point."""

    base_mean: float
    fut_mean: float
    fut_min: float
    fut_max: float
    base_trop: float | None
    fut_trop: float | None
    models: tuple[str, ...]


def point_stats(rows: Sequence[HeatPoint]) -> PointStats | None:
    """Ensemble mean/min/max of future hot days and means of base hot days / tropical nights."""
    full = [r for r in rows if r.base_hot_days is not None and r.fut_hot_days is not None]
    if not full:
        return None
    fut = ensemble([r.fut_hot_days for r in full])
    base = ensemble([r.base_hot_days for r in full])
    base_trop = ensemble([r.base_trop_nights for r in full])
    fut_trop = ensemble([r.fut_trop_nights for r in full])
    assert fut is not None
    assert base is not None
    return PointStats(
        base_mean=base[0],
        fut_mean=fut[0],
        fut_min=fut[1],
        fut_max=fut[2],
        base_trop=base_trop[0] if base_trop else None,
        fut_trop=fut_trop[0] if fut_trop else None,
        models=tuple(sorted(r.model for r in full)),
    )


def grid_reference(session: Session) -> list[float]:
    """Ensemble-mean future hot days of every grid point that has all three models."""
    rows = session.execute(
        text(
            """
            select avg(fut_hot_days) as v from heat_point
            where kind = 'grid' and fut_hot_days is not null
            group by lat_r, lon_r having count(*) = :n
            """
        ),
        {"n": len(MODELS)},
    ).all()
    return sorted(float(r.v) for r in rows)


def percentile_of(value: float, reference: Sequence[float]) -> float | None:
    """Share of reference values that are <= ``value`` (0-1); ``None`` without a reference."""
    if not reference:
        return None
    return sum(1 for v in reference if v <= value) / len(reference)


def point_rows(session: Session, lat: float, lon: float) -> list[HeatPoint]:
    """Stored rows of one point."""
    return list(
        session.scalars(
            select(HeatPoint).where(
                HeatPoint.lat_r == round(lat, 3), HeatPoint.lon_r == round(lon, 3)
            )
        )
    )


def nearest_full_point(
    session: Session, lat: float, lon: float
) -> tuple[float, float, float] | None:
    """Nearest stored *full* point within ``APPROX_MAX_KM`` as ``(lat, lon, km)``."""
    rows = session.execute(
        text(
            """
            select lat_r::float as lat, lon_r::float as lon from heat_point
            where base_hot_days is not null and fut_trop_nights is not null
            group by lat_r, lon_r having count(*) = :n
            """
        ),
        {"n": len(MODELS)},
    ).all()
    best: tuple[float, float, float] | None = None
    for r in rows:
        d = km_between(lat, lon, r.lat, r.lon)
        if d <= APPROX_MAX_KM and (best is None or d < best[2]):
            best = (r.lat, r.lon, d)
    return best


def build_heat_cells(session: Session, lau_id: str) -> dict[str, int]:
    """Fill ``heat_cell`` for the inhabited cells of a municipality from the stored heat points.

    A cell uses the full point of its own 0.1 degree coordinates; when that point has not been fetched
    the nearest full point within 25 km is used and counted as ``approximate``; cells with neither stay
    without heat data (the exposure result reports the coverage).
    """
    reference = grid_reference(session)
    cells = session.execute(
        text(
            """
            select grd_id, ST_Y(centroid)::float as lat, ST_X(centroid)::float as lon from cell
            where lau_id = :lau and coalesce(pop_total, 0) > 0
            """
        ),
        {"lau": lau_id},
    ).all()
    cache: dict[tuple[float, float], tuple[PointStats, float, float, bool] | None] = {}
    exact = approx = missing = 0
    out: list[dict[str, Any]] = []
    for c in cells:
        key = (round_coord(c.lat), round_coord(c.lon))
        if key not in cache:
            stats = point_stats(point_rows(session, *key))
            if stats is not None:
                cache[key] = (stats, key[0], key[1], False)
            else:
                near = nearest_full_point(session, *key)
                near_stats = point_stats(point_rows(session, near[0], near[1])) if near else None
                cache[key] = (near_stats, near[0], near[1], True) if near_stats and near else None
        hit = cache[key]
        if hit is None:
            missing += 1
            continue
        stats, plat, plon, is_approx = hit
        pct = percentile_of(stats.fut_mean, reference)
        if pct is None:
            missing += 1
            continue
        approx += is_approx
        exact += not is_approx
        out.append(
            {
                "grd_id": c.grd_id,
                "base_mean": stats.base_mean,
                "fut_mean": stats.fut_mean,
                "fut_min": stats.fut_min,
                "fut_max": stats.fut_max,
                "base_trop": stats.base_trop,
                "fut_trop": stats.fut_trop,
                "percentile": pct,
                "lat_r": round(plat, 3),
                "lon_r": round(plon, 3),
            }
        )
    ids = [c.grd_id for c in cells]
    if ids:
        session.execute(delete(HeatCell).where(HeatCell.grd_id.in_(ids)))
    for i in range(0, len(out), 2000):
        session.execute(insert(HeatCell).values(out[i : i + 2000]))
    session.commit()
    return {
        "cells": len(cells),
        "heat_exact": exact,
        "heat_approximate": approx,
        "heat_missing": missing,
        "grid_points": len(reference),
    }


# ---------------------------------------------------------------------------- job


def run_heat_job(
    client: OpenMeteoClient,
    session: Session,
    *,
    lau_ids: Sequence[str] = (),
    grid_first: int = 30,
    max_requests: int | None = None,
) -> dict[str, int]:
    """Fetch what is missing, in this order: ``grid_first`` grid points, the points of the given
    municipalities, then the rest of the grid. Resumable (stored points are skipped); respects the quota."""
    grid = grid_lattice(session)
    plan: list[tuple[str, float, float]] = [("grid", la, lo) for la, lo in grid[:grid_first]]
    for lau in lau_ids:
        plan += [("full", la, lo) for la, lo in demo_points(session, lau)]
    plan += [("grid", la, lo) for la, lo in grid[grid_first:]]
    done = skipped = 0
    for kind, la, lo in plan:
        have = stored_models(session, la, lo, full=(kind == "full"))
        if len(have) >= len(MODELS):
            skipped += 1
            continue
        if max_requests is not None and done >= max_requests:
            break
        fetch = fetch_full_point if kind == "full" else fetch_grid_point
        got = fetch(client, session, la, lo, batch=True)
        done += 1
        log.info(
            "heat_point", kind=kind, lat=la, lon=lo, models=len(got), done=done, planned=len(plan)
        )
    return {"fetched": done, "skipped": skipped, "planned": len(plan)}
