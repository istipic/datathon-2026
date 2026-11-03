"""``blizu validate``: compare our network distances with OSRM (foot profile).

For random (origin node, category) pairs we take our distance to the nearest facility and ask
OSRM for the walking route between the same two network nodes. OSRM is queried at most once per
second (public demo server). Results go to ``apps/blizu/docs/validation.md``.
"""

from __future__ import annotations

import random
import statistics
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx
import numpy as np
import structlog
from scipy.spatial import cKDTree

from blizu_api.constants import CATEGORIES
from blizu_api.db import make_session_factory
from blizu_api.ingest.access import load_access_arrays, load_facility_frame
from blizu_api.ingest.graph import load_graph
from blizu_api.manifest import Manifest
from blizu_api.settings import BlizuSettings
from opendata_core import http as http_mod

log = structlog.get_logger(__name__)

OSRM_BASE = "https://routing.openstreetmap.de/routed-foot"
MIN_PAIR_M = 300.0  # skip trivial pairs
MAX_PAIR_M = 3500.0
SEED = 2026
REPORT = Path("apps/blizu/docs/validation.md")


@dataclass(frozen=True)
class Pair:
    """One validated origin/destination pair."""

    category: str
    origin: tuple[float, float]  # lon, lat
    dest: tuple[float, float]
    ours_m: float
    osrm_m: float | None


def summarise(pairs: list[Pair]) -> dict[str, float]:
    """MAE (m), mean error (m), median ours/OSRM ratio and share within +-20 % over valid pairs."""
    ok = [p for p in pairs if p.osrm_m]
    if not ok:
        return {}
    errors = [p.ours_m - float(p.osrm_m) for p in ok]  # type: ignore[arg-type]
    ratios = [p.ours_m / float(p.osrm_m) for p in ok]  # type: ignore[arg-type]
    return {
        "n": float(len(ok)),
        "mae_m": statistics.mean(abs(e) for e in errors),
        "mean_error_m": statistics.mean(errors),
        "median_ratio": statistics.median(ratios),
        "within_20pct": sum(0.8 <= r <= 1.2 for r in ratios) / len(ratios),
    }


def osrm_distance(
    client: httpx.Client, a: tuple[float, float], b: tuple[float, float]
) -> float | None:
    """Walking distance in metres between two lon/lat points from OSRM, or None if no route."""
    url = f"{OSRM_BASE}/route/v1/driving/{a[0]:.6f},{a[1]:.6f};{b[0]:.6f},{b[1]:.6f}"
    data = http_mod.get_json(client, url, {"overview": "false", "alternatives": "false"})
    if data.get("code") != "Ok" or not data.get("routes"):
        return None
    return float(data["routes"][0]["distance"])


def pick_pairs(settings: BlizuSettings, samples: int) -> list[Pair]:
    """Random pairs with our distance (no OSRM yet), deterministic for a fixed seed."""
    manifest = Manifest(settings.derived_dir)
    graph = load_graph(manifest.path_of("graph"))
    arrays = load_access_arrays(settings.derived_dir, manifest)
    with make_session_factory(settings)() as session:
        facilities = load_facility_frame(session).set_index("id", drop=False)
    tree = cKDTree(np.column_stack([graph.x, graph.y]))
    rng = random.Random(SEED)  # noqa: S311 - reproducible sampling, not cryptography
    categories = [
        c for c in CATEGORIES if c != "park"
    ]  # parks are reached via several access points
    pairs: list[Pair] = []
    attempts = 0
    while len(pairs) < samples and attempts < samples * 400:
        attempts += 1
        category = rng.choice(categories)
        dist, fids = arrays[("full", category)]
        node = rng.randrange(graph.n_nodes)
        d = float(dist[node])
        fid = int(fids[node])
        if not (MIN_PAIR_M <= d <= MAX_PAIR_M) or fid not in facilities.index:
            continue
        fac = facilities.loc[fid]
        # the facility's network node: the nearest node to its point (as in the access step)
        from pyproj import Transformer

        from blizu_api.constants import CRS_METRIC, CRS_WGS84

        x, y = Transformer.from_crs(CRS_WGS84, CRS_METRIC, always_xy=True).transform(
            fac["lon"], fac["lat"]
        )
        _, dest_node = tree.query([x, y])
        pairs.append(
            Pair(
                category,
                (float(graph.lon[node]), float(graph.lat[node])),
                (float(graph.lon[dest_node]), float(graph.lat[dest_node])),
                d,
                None,
            )
        )
    return pairs


def render_report(
    pairs: list[Pair], stats: dict[str, float], settings: BlizuSettings, status: str
) -> str:
    """Markdown report."""
    lines = [
        "# Validacija pješačkih udaljenosti (Blizu)",
        "",
        f"Generirano: {datetime.now(UTC).isoformat(timespec='seconds')} (UTC), naredba `blizu validate`.",
        "",
        f"**Status:** {status}",
        "",
        "## Metoda",
        "",
        "- 20 nasumičnih parova (čvor mreže → najbliži objekt kategorije), `seed = 2026`; izuzeti su parkovi "
        "(više pristupnih točaka) i trivijalni parovi (< 300 m, > 3,5 km).",
        "- *Naša udaljenost*: najkraći put po grafu Blizu (OSM pješačka mreža, `scipy` Dijkstra, puni graf).",
        f"- *Referenca*: OSRM profil za pješake, `{OSRM_BASE}/route/v1/driving/…` (profil „foot” "
        "poslužitelja routing.openstreetmap.de), najviše 1 zahtjev u sekundi.",
        "- Isti OSM podaci, ali drukčiji algoritam i drukčije čišćenje mreže, pa se razlike očekuju "
        "(OSRM sam „hvata” točke na svoju mrežu).",
        "",
    ]
    if stats:
        lines += [
            "## Rezultat",
            "",
            f"| Pokazatelj | Vrijednost |\n|---|---|\n| Valjanih parova | {int(stats['n'])} |\n"
            f"| MAE (m) | {stats['mae_m']:.0f} |\n"
            f"| Srednja pogreška (naša − OSRM, m) | {stats['mean_error_m']:+.0f} |\n"
            f"| Medijan omjera (naša / OSRM) | {stats['median_ratio']:.3f} |\n"
            f"| Udio unutar ±20 % | {stats['within_20pct'] * 100:.0f} % |",
            "",
        ]
    lines += [
        "## Parovi",
        "",
        "| # | Kategorija | Naša (m) | OSRM (m) | Omjer |",
        "|---|---|---:|---:|---:|",
    ]
    for i, p in enumerate(pairs, 1):
        osrm = "–" if p.osrm_m is None else f"{p.osrm_m:.0f}"
        ratio = "–" if not p.osrm_m else f"{p.ours_m / p.osrm_m:.3f}"
        lines.append(f"| {i} | {p.category} | {p.ours_m:.0f} | {osrm} | {ratio} |")
    lines.append("")
    return "\n".join(lines)


def run_validation(
    settings: BlizuSettings, samples: int = 20, report: Path = REPORT
) -> dict[str, Any]:
    """Run the comparison and write the report. Skips (and says so) if OSRM is unreachable."""
    pairs = pick_pairs(settings, samples)
    log.info("validation_pairs", n=len(pairs))
    results: list[Pair] = []
    status = "OK"
    with http_mod.make_client(settings) as client:
        for i, p in enumerate(pairs):
            try:
                dist = osrm_distance(client, p.origin, p.dest)
            except (httpx.HTTPError, ValueError) as exc:
                if i == 0:
                    status = (
                        f"PRESKOČENO: OSRM nije dostupan ({type(exc).__name__}: {str(exc)[:120]})"
                    )
                    log.warning("osrm_unreachable", error=str(exc)[:200])
                    results = list(pairs)
                    break
                dist = None
                status = "DJELOMIČNO: neki zahtjevi prema OSRM-u nisu uspjeli"
            results.append(Pair(p.category, p.origin, p.dest, p.ours_m, dist))
            time.sleep(1.0)  # public server: <= 1 request/second
    stats = summarise(results)
    report.parent.mkdir(parents=True, exist_ok=True)
    report.write_text(render_report(results, stats, settings, status), encoding="utf-8")
    log.info("validation_done", status=status, **stats)
    return {"status": status, **stats}
