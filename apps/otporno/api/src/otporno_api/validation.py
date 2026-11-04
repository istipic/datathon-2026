"""``otporno validate``: reproducible Karlovac sample for a human check and a Zagreb Grič heat line."""

from __future__ import annotations

import csv
import random
from pathlib import Path
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from otporno_api.constants import FLOOD_UNAVAILABLE
from otporno_api.heat import point_rows, point_stats, round_coord
from otporno_api.settings import OtpornoSettings

KARLOVAC = "HR_01791"
N_POINTS = 30
ZAGREB_GRIC = (45.8139, 15.9775)  # Grič meteorological station, Zagreb
DHMZ_NORMALS_URL = "https://meteo.hr/klima.php?section=klima_pracenje&param=klimatske_normale"
HV_VIEWER_URL = "https://www.voda.hr/hr/karte-opasnosti-od-poplava-i-karte-rizika-od-poplava-2019"
COLUMNS = [
    "id",
    "lat",
    "lon",
    "grd_id",
    "app_flood",
    "hv_viewer_high",
    "hv_viewer_medium",
    "hv_viewer_low",
    "checked_by",
    "checked_on",
    "notes",
]


def sample_points(
    session: Session, lau_id: str = KARLOVAC, n: int = N_POINTS, seed: int = 2026
) -> list[dict[str, Any]]:
    """``n`` inhabited-cell centroids of the municipality, drawn with a fixed seed (population-weighted)."""
    rows = session.execute(
        text(
            "select grd_id, ST_Y(centroid)::float lat, ST_X(centroid)::float lon, pop_total from cell "
            "where lau_id = :l and coalesce(pop_total, 0) > 0 order by grd_id"
        ),
        {"l": lau_id},
    ).all()
    rng = random.Random(seed)  # noqa: S311 (reproducible sampling, not security)
    pool = list(rows)
    picked: list[Any] = []
    while pool and len(picked) < n:
        choice = rng.choices(pool, weights=[float(r.pop_total) for r in pool], k=1)[0]
        pool.remove(choice)
        picked.append(choice)
    picked.sort(key=lambda r: r.grd_id)
    return [
        {"id": i + 1, "lat": round(r.lat, 5), "lon": round(r.lon, 5), "grd_id": r.grd_id}
        for i, r in enumerate(picked)
    ]


def run_validation(
    session: Session, settings: OtpornoSettings, out: str, seed: int
) -> dict[str, Any]:
    """Write the CSV template and return the printed summary."""
    points = sample_points(session, seed=seed)
    path = Path(out)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=COLUMNS)
        w.writeheader()
        for p in points:
            w.writerow(
                {
                    **p,
                    "app_flood": FLOOD_UNAVAILABLE,
                    **{c: "" for c in COLUMNS if c not in p and c != "app_flood"},
                }
            )
    key = (round_coord(ZAGREB_GRIC[0]), round_coord(ZAGREB_GRIC[1]))
    stats = point_stats(point_rows(session, *key))
    return {
        "csv": str(path),
        "points": len(points),
        "seed": seed,
        "hv_viewer": HV_VIEWER_URL,
        "how_to": "For each point open the viewer, switch on the three 2019 scenarios and write true/false per scenario.",
        "zagreb_gric": {
            "model_point": {"lat": key[0], "lon": key[1]},
            "base_hot_days_1991_2020": None if stats is None else round(stats.base_mean, 1),
            "models": None if stats is None else list(stats.models),
            "dhmz_normals": DHMZ_NORMALS_URL,
            "note": "Compare by hand with the DHMZ normals for Zagreb-Grič; the modelled value is a 0.1 degree grid value.",
        },
    }
