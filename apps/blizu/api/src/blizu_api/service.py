"""Business logic of ``/access`` and ``/compare`` (kept free of FastAPI for testing)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import numpy as np

from blizu_api.constants import ADDRESS_SNAP_MAX_M, CATEGORIES, DIJKSTRA_LIMIT_M
from blizu_api.scoring import (
    category_confidence,
    confidence_label,
    grade,
    minutes,
    overall_confidence,
    renormalised_index,
    score,
)
from blizu_api.store import DataStore

WARN_SNAP_M = 150.0
STALE_DAYS = 365


class OutsideZagrebError(ValueError):
    """The point is not inside the Grad Zagreb boundary."""


class FarFromNetworkError(ValueError):
    """The point is too far from the walking network."""

    def __init__(self, snapped_m: float) -> None:
        super().__init__("adresa daleko od pješačke mreže")
        self.snapped_m = snapped_m


def _days_text(days: float) -> str:
    if days < 730:
        return f"{round(days)} dana"
    return f"{days / 365.25:.1f}".replace(".", ",") + " godina"


def display_name(store: DataStore, category: str, name: str | None) -> str:
    """Facility name, or an honest placeholder when the source has none."""
    return name or f"{store.cfg.categories[category].label} (naziv nije u izvoru)"


def resolve_origin(store: DataStore, lat: float, lon: float) -> tuple[int, float]:
    """Graph node and snap distance (m) of an address; the validation shared by every endpoint.

    Raises :class:`OutsideZagrebError` (outside Grad Zagreb) and :class:`FarFromNetworkError`
    (> 300 m from the walking network).
    """
    if not store.inside_boundary(lon, lat):
        raise OutsideZagrebError("Adresa nije unutar Grada Zagreba.")
    node, snapped = store.snap(lon, lat)
    if snapped > ADDRESS_SNAP_MAX_M:
        raise FarFromNetworkError(snapped)
    return node, snapped


def compute_access(
    store: DataStore, lat: float, lon: float, persona: str, now: datetime | None = None
) -> dict[str, Any]:
    """Index, grade, confidence and per-category walking minutes for an address."""
    node, snapped = resolve_origin(store, lat, lon)

    cfg = store.cfg
    p = cfg.personas[persona]
    warnings: list[str] = []
    if snapped > WARN_SNAP_M:
        warnings.append(
            f"Adresa je {round(snapped)} m od najbliže pješačke staze; stvarno vrijeme može biti dulje."
        )
    if p.graph == "wheelchair":
        warnings.append(
            "Graf za invalidska kolica izostavlja stepenice i staze označene wheelchair=no u OpenStreetMapu; "
            "podaci o pristupačnosti nisu potpuni."
        )

    rows: list[dict[str, Any]] = []
    index_items: list[tuple[float, float]] = []
    conf_items: list[tuple[float, float]] = []
    for cid in CATEGORIES:
        cat = cfg.categories[cid]
        weight = cat.weights[persona]
        row: dict[str, Any] = {
            "category": cid,
            "label": cat.label,
            "minutes": None,
            "score": 0.0,
            "weight": weight,
            "nearest": None,
            "tier": None,
            "freshness_days": None,
            "confidence": None,
            "has_data": cid in store.categories_with_data,
            "good_min": cat.good_min,
            "max_min": cat.max_min,
        }
        if cid not in store.categories_with_data:
            warnings.append(
                f"{cat.label}: nema učitanih podataka, kategorija nije uključena u indeks."
            )
            rows.append(row)
            continue
        dist, fids = store.distance_array(persona, cid)
        d = float(dist[node])
        if np.isfinite(d):
            total_m = snapped + d
            t = minutes(total_m, p.speed_mps)
            s = score(t, cat.good_min, cat.max_min)
            fac = store.facility(int(fids[node]))
            row.update(minutes=round(t, 1), score=round(s, 3), distance_m=round(total_m))
            if fac:
                row["nearest"] = {
                    "name": display_name(store, cid, fac["name"]),
                    "address": fac["address"],
                    "lon": fac["lon"],
                    "lat": fac["lat"],
                    "source_id": fac["source_id"],
                }
                row["tier"] = fac["tier"]
                days = store.source_days(fac["source_id"])
                row["freshness_days"] = None if days is None else round(days)
                if days is not None and days > STALE_DAYS and fac["source_id"] != "osm-zagreb":
                    warnings.append(f"{cat.label}: podaci su stari {_days_text(days)}.")
        else:
            row["beyond_limit_m"] = DIJKSTRA_LIMIT_M
            warnings.append(
                f"{cat.label}: najbliži objekt je dalje od {round(DIJKSTRA_LIMIT_M / 1000)} km hoda."
            )
        # confidence: tier and age of the nearest facility's source (dominant source if none nearby)
        tier = row["tier"] or store.default_tier(cid)
        days = (
            row["freshness_days"] if row["freshness_days"] is not None else store.default_days(cid)
        )
        conf = category_confidence(tier, days, cfg)
        row["confidence"] = round(conf, 3)
        if row["tier"] is None:
            row["tier"] = tier
        if weight > 0:
            index_items.append((weight, row["score"]))
            conf_items.append((weight, conf))
        rows.append(row)

    idx = renormalised_index(index_items)
    overall = overall_confidence(conf_items)
    if idx is None:
        warnings.append("Nema dovoljno podataka za izračun indeksa.")
    return {
        "index": idx,
        "grade": None if idx is None else grade(idx, cfg.grades),
        "confidence": None
        if overall is None
        else {
            "value": round(overall, 3),
            "label": confidence_label(overall, cfg.confidence_labels),
        },
        "persona": persona,
        "snapped_distance_m": round(snapped, 1),
        "categories": rows,
        "warnings": warnings,
        "scoring_version": cfg.version,
        "computed_at": (now or datetime.now(UTC)).isoformat(),
    }


def compare(
    store: DataStore, a: tuple[float, float], b: tuple[float, float], persona: str
) -> dict[str, Any]:
    """Two addresses side by side with per-category differences (b minus a)."""
    ra = compute_access(store, a[0], a[1], persona)
    rb = compute_access(store, b[0], b[1], persona)
    diffs = []
    for ca, cb in zip(ra["categories"], rb["categories"], strict=True):
        ma, mb = ca["minutes"], cb["minutes"]
        diffs.append(
            {
                "category": ca["category"],
                "label": ca["label"],
                "minutes_diff": None if ma is None or mb is None else round(mb - ma, 1),
                "score_diff": round(cb["score"] - ca["score"], 3),
            }
        )
    index_diff = None if ra["index"] is None or rb["index"] is None else rb["index"] - ra["index"]
    return {"persona": persona, "a": ra, "b": rb, "differences": diffs, "index_diff": index_diff}
