"""Municipal exposure: people and 65+ residents per hazard and band, status of the precompute, cell GeoJSON."""

from __future__ import annotations

import json
from collections import OrderedDict
from datetime import UTC, datetime
from typing import Any

import numpy as np
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from otporno_api.constants import BANDS, FLOOD_UNAVAILABLE
from otporno_api.db import Municipality, PrecomputeStatus
from otporno_api.flood import flood_score
from otporno_api.heat import band_of, build_heat_cells
from otporno_api.priority import HAZARDS, cell_priority, effective_weights, validate_weights

DEMO = {"HR_01791": "Karlovac", "HR_01333": "Zagreb"}  # precomputed demo municipalities


def set_status(
    session: Session,
    lau_id: str,
    status: str,
    message: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    """Upsert the precompute status row."""
    now = datetime.now(UTC)
    values = {
        "lau_id": lau_id,
        "status": status,
        "message": message,
        "details": details or {},
        "started_at": now if status == "computing" else None,
        "finished_at": now if status in ("ready", "unavailable", "failed") else None,
    }
    stmt = insert(PrecomputeStatus).values(values)
    update = {k: getattr(stmt.excluded, k) for k in ("status", "message", "details", "finished_at")}
    if status == "computing":
        update["started_at"] = stmt.excluded.started_at
    session.execute(stmt.on_conflict_do_update(index_elements=["lau_id"], set_=update))
    session.commit()


def compute_municipality(session: Session, lau_id: str) -> dict[str, Any]:
    """Build the heat cells of a municipality from the stored heat points and record the result.

    Flood is not classified (ladder c) and fire is P1, so the status is ``ready`` as soon as the heat
    layer exists for at least one cell; the coverage of the heat layer is part of the details.
    """
    heat = build_heat_cells(session, lau_id)
    sites = int(
        session.scalar(text("select count(*) from candidate_site where lau_id = :l"), {"l": lau_id})
        or 0
    )
    details = {
        "heat": heat,
        "candidate_sites": sites,
        "flood": {"status": "unavailable", "ladder": "c"},
        "fire": {"status": "unavailable"},
    }
    with_heat = heat["heat_exact"] + heat["heat_approximate"]
    if with_heat == 0:
        msg = (
            "Nema klimatskih podataka za ovu općinu: izračun se oslanja na modelske točke koje se dohvaćaju "
            "postupno zbog ograničenja usluge Open-Meteo."
        )
        set_status(session, lau_id, "unavailable", msg, details)
        return {"status": "unavailable", "message": msg, "details": details}
    set_status(session, lau_id, "ready", None, details)
    return {"status": "ready", "details": details}


def get_status(session: Session, lau_id: str) -> dict[str, Any]:
    """Current precompute state (``not_started`` when never computed)."""
    row = session.get(PrecomputeStatus, lau_id)
    if row is None:
        return {
            "status": "not_started",
            "message": None,
            "details": {},
            "started_at": None,
            "finished_at": None,
        }
    return {
        "status": row.status,
        "message": row.message,
        "details": row.details or {},
        "started_at": row.started_at.isoformat() if row.started_at else None,
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
    }


def _cells(session: Session, lau_id: str) -> list[Any]:
    return list(
        session.execute(
            text(
                """
                select c.grd_id, c.pop_total, c.pop_65p, h.percentile, h.fut_mean, h.base_mean, h.fut_min, h.fut_max,
                       ST_AsGeoJSON(c.geom, 5) as geojson
                from cell c left join heat_cell h using (grd_id)
                where c.lau_id = :lau and coalesce(c.pop_total, 0) > 0
                order by c.grd_id
                """
            ),
            {"lau": lau_id},
        )
    )


def municipality_info(session: Session, lau_id: str) -> dict[str, Any] | None:
    """Name and basic population numbers of a municipality, or ``None`` if unknown."""
    m = session.get(Municipality, lau_id)
    if m is None:
        return None
    pop = session.execute(
        text(
            "select count(*) filter (where coalesce(pop_total,0) > 0) cells, coalesce(sum(pop_total),0) pt, coalesce(sum(pop_65p),0) p65 from cell where lau_id = :l"
        ),
        {"l": lau_id},
    ).one()
    return {
        "lau_id": m.lau_id,
        "name": m.name,
        "area_km2": m.area_km2,
        "cells": int(pop.cells),
        "pop_total": int(pop.pt),
        "pop_65p": int(pop.p65),
        "demo": lau_id in DEMO,
    }


def exposure(session: Session, lau_id: str) -> dict[str, Any] | None:
    """Per hazard and band: cells, residents, residents 65+ (``GET /municipalities/{id}/exposure``)."""
    info = municipality_info(session, lau_id)
    if info is None:
        return None
    status = get_status(session, lau_id)
    cells = _cells(session, lau_id)
    heat_bands: dict[str, dict[str, int]] = OrderedDict(
        (b, {"cells": 0, "pop_total": 0, "pop_65p": 0}) for b in BANDS
    )
    no_heat = {"cells": 0, "pop_total": 0, "pop_65p": 0}
    for c in cells:
        if c.percentile is None:
            no_heat["cells"] += 1
            no_heat["pop_total"] += int(c.pop_total or 0)
            no_heat["pop_65p"] += int(c.pop_65p or 0)
            continue
        b = heat_bands[band_of(float(c.percentile)) or BANDS[0]]
        b["cells"] += 1
        b["pop_total"] += int(c.pop_total or 0)
        b["pop_65p"] += int(c.pop_65p or 0)
    heat_ready = any(b["cells"] for b in heat_bands.values())
    high65 = heat_bands["visoka"]["pop_65p"] + heat_bands["vrlo visoka"]["pop_65p"]
    return {
        "municipality": info,
        "status": status["status"],
        "message": status["message"],
        "started_at": status["started_at"],
        "finished_at": status["finished_at"],
        "hazards": {
            "flood": {"status": "unavailable", "message": FLOOD_UNAVAILABLE, "bands": []},
            "heat": {
                "status": "ready" if heat_ready else "unavailable",
                "bands": [{"band": k, **v} for k, v in heat_bands.items()],
                "without_data": no_heat,
                "coverage": (status["details"] or {}).get("heat"),
            },
            "fire": {
                "status": "unavailable",
                "message": "Procjena požara (P1) nije učitana.",
                "bands": [],
            },
        },
        "kpis": {
            "flood_high_pop": None,
            "flood_high_pop_65p": None,
            "heat_high_pop_65p": high65 if heat_ready else None,
            "heat_high_pop": (
                heat_bands["visoka"]["pop_total"] + heat_bands["vrlo visoka"]["pop_total"]
            )
            if heat_ready
            else None,
        },
    }


def priority_classes(values: list[float], n: int = 5) -> list[float]:
    """Quantile breaks (n - 1 thresholds) of the positive priorities, for a consistent colour scale."""
    pos = np.array([v for v in values if v > 0])
    if pos.size < n:
        return [float(x) for x in np.unique(pos)][: n - 1]
    return [float(np.quantile(pos, q)) for q in np.linspace(0, 1, n + 1)[1:-1]]


def cells_geojson(
    session: Session, lau_id: str, weights: dict[str, float]
) -> dict[str, Any] | None:
    """Cells of a municipality as GeoJSON with scores, bands and priority (``/cells``)."""
    if municipality_info(session, lau_id) is None:
        return None
    w = validate_weights(weights)
    cells = _cells(session, lau_id)
    has_heat = any(c.percentile is not None for c in cells)
    eff = effective_weights(w, {"flood": False, "heat": has_heat, "fire": False})
    features = []
    prios = []
    for c in cells:
        heat = float(c.percentile) if c.percentile is not None else None
        scores = {"flood": flood_score(None), "heat": heat, "fire": None}
        prio = cell_priority(scores, w, c.pop_total, c.pop_65p)
        prios.append(prio)
        features.append(
            {
                "type": "Feature",
                "geometry": json.loads(c.geojson),
                "properties": {
                    "grd_id": c.grd_id,
                    "pop_total": int(c.pop_total or 0),
                    "pop_65p": int(c.pop_65p or 0),
                    "heat_score": None if heat is None else round(heat, 4),
                    "heat_band": band_of(heat),
                    "heat_fut_days": None if c.fut_mean is None else round(float(c.fut_mean), 1),
                    "heat_base_days": None if c.base_mean is None else round(float(c.base_mean), 1),
                    "flood_level": None,
                    "fire_score": None,
                    "priority": round(prio, 3),
                },
            }
        )
    breaks = priority_classes(prios)
    for f in features:
        p = f["properties"]["priority"]
        f["properties"]["priority_class"] = sum(1 for b in breaks if p > b) if p > 0 else -1
    return {
        "type": "FeatureCollection",
        "features": features,
        "summary": {
            "lau_id": lau_id,
            "cells": len(features),
            "weights": w,
            "weights_effective": eff,
            "breaks": breaks,
            "pop_total": sum(f["properties"]["pop_total"] for f in features),
            "pop_65p": sum(f["properties"]["pop_65p"] for f in features),
            "flood": "unavailable",
        },
    }


def search_municipalities(session: Session, q: str, limit: int = 15) -> list[dict[str, Any]]:
    """Municipalities whose name contains ``q`` (case-insensitive), with population and precompute status."""
    rows = session.execute(
        text(
            """
            select m.lau_id, m.name, coalesce(sum(c.pop_total), 0) as pop, coalesce(p.status, 'not_started') as status
            from municipality m
            left join cell c on c.lau_id = m.lau_id
            left join precompute_status p on p.lau_id = m.lau_id
            where m.name ilike :pat
            group by m.lau_id, m.name, p.status
            order by (lower(m.name) = lower(:q)) desc, pop desc
            limit :lim
            """
        ),
        {"pat": f"%{q.strip()}%", "q": q.strip(), "lim": limit},
    ).all()
    return [
        {
            "lau_id": r.lau_id,
            "name": r.name,
            "pop_total": int(r.pop),
            "status": r.status,
            "demo": r.lau_id in DEMO,
        }
        for r in rows
    ]


def municipality_of_point(session: Session, lat: float, lon: float) -> dict[str, Any] | None:
    """The municipality that contains the point (a point up to 500 m outside the simplified outline counts)."""
    row = session.execute(
        text(
            """
            select lau_id, name from municipality
            where ST_Intersects(geom, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326))
            union all
            select lau_id, name from (
                select lau_id, name from municipality
                where ST_DWithin(geom::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography, 500)
                order by ST_Distance(geom::geography, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326)::geography) limit 1
            ) near
            limit 1
            """
        ),
        {"lon": lon, "lat": lat},
    ).first()
    return {"lau_id": row.lau_id, "name": row.name} if row else None


__all__ = [
    "DEMO",
    "HAZARDS",
    "cells_geojson",
    "compute_municipality",
    "exposure",
    "get_status",
    "municipality_info",
    "municipality_of_point",
    "search_municipalities",
    "select",
    "set_status",
]
