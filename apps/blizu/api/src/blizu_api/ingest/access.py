"""Access distances: for every graph node, network distance to the nearest facility per category."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import structlog
from pyproj import Transformer
from scipy.sparse.csgraph import dijkstra
from sqlalchemy import text
from sqlalchemy.orm import Session

from blizu_api.constants import (
    CATEGORIES,
    CRS_METRIC,
    CRS_WGS84,
    DIJKSTRA_LIMIT_M,
    SNAP_MAX_M,
    SRC_GRAPH,
    VARIANTS,
)
from blizu_api.ingest.graph import GraphData, load_graph
from blizu_api.manifest import Manifest, sha256_file
from blizu_api.settings import BlizuSettings
from opendata_core.geo import snap_points_to_nodes
from opendata_core.provenance import record_ingestion

log = structlog.get_logger(__name__)


@dataclass
class SnapResult:
    """Facility access nodes for one category."""

    nodes: np.ndarray  # graph node index per access point
    facility_ids: np.ndarray  # facility id per access point (same length)
    dropped: pd.DataFrame  # facilities with no access point within the snap distance
    total: int


def load_facility_frame(session: Session) -> pd.DataFrame:
    """All facilities: id, category, name, source_id, tier, lon, lat, attrs."""
    rows = session.execute(
        text(
            "select id, category, name, address, source_id, tier, st_x(geom) as lon, st_y(geom) as lat, "
            "attrs from facility order by id"
        )
    ).mappings()
    return pd.DataFrame([dict(r) for r in rows])


def access_points(row: Any) -> list[tuple[float, float]]:
    """(lon, lat) points through which a facility is reached (parks: centroid + boundary points)."""
    attrs = row.attrs or {}
    extra = attrs.get("access_points") if isinstance(attrs, dict) else None
    if extra:
        return [(float(lon), float(lat)) for lon, lat in extra]
    return [(float(row.lon), float(row.lat))]


def snap_facilities(
    facilities: pd.DataFrame, graph: GraphData, max_dist_m: float = SNAP_MAX_M
) -> SnapResult:
    """Snap each facility's access points to the nearest node (<= ``max_dist_m``)."""
    tr = Transformer.from_crs(CRS_WGS84, CRS_METRIC, always_xy=True)
    pts: list[tuple[float, float]] = []
    owner: list[int] = []
    for row in facilities.itertuples(index=False):
        for lon, lat in access_points(row):
            x, y = tr.transform(lon, lat)
            pts.append((x, y))
            owner.append(int(row.id))
    if not pts:
        return SnapResult(np.empty(0, int), np.empty(0, int), facilities.iloc[0:0], 0)
    xy = np.asarray(pts)
    nodes_xy = np.column_stack([graph.x, graph.y])
    idx, dist = snap_points_to_nodes(xy, nodes_xy, max_dist_m)
    owner_arr = np.asarray(owner)
    ok = idx >= 0
    snapped_ids = set(owner_arr[ok].tolist())
    dropped = facilities[~facilities["id"].isin(snapped_ids)].copy()
    if len(dropped):
        # report the real distance of dropped facilities to the network
        _, far = snap_points_to_nodes(xy, nodes_xy, 1e9)
        first = {}
        for o, d in zip(owner, far, strict=True):
            first[o] = min(first.get(o, np.inf), float(d))
        dropped["nearest_node_m"] = dropped["id"].map(first).round(1)
    return SnapResult(
        idx[ok].astype(np.int64), owner_arr[ok].astype(np.int64), dropped, len(facilities)
    )


def nearest_facility_distances(
    graph: GraphData, variant: str, snap: SnapResult, limit_m: float = DIJKSTRA_LIMIT_M
) -> tuple[np.ndarray, np.ndarray]:
    """Network distance (m) from every node to the nearest facility, and that facility's id.

    ``inf`` / ``-1`` beyond ``limit_m`` (or with no facilities).
    """
    n = graph.n_nodes
    if len(snap.nodes) == 0:
        return np.full(n, np.inf, dtype=np.float32), np.full(n, -1, dtype=np.int64)
    dist, _pred, src = dijkstra(
        graph.variant(variant),
        directed=False,
        indices=snap.nodes,
        min_only=True,
        limit=limit_m,
        return_predecessors=True,
    )
    # With min_only=True scipy returns, per node, the GRAPH NODE that is its nearest source.
    # Map source nodes back to facility ids (several facilities on one node: lowest id wins).
    node_to_fac = np.full(n, -1, dtype=np.int64)
    for node, fid in sorted(
        zip(snap.nodes.tolist(), snap.facility_ids.tolist(), strict=True), key=lambda t: -t[1]
    ):
        node_to_fac[node] = fid
    fac = np.where(src >= 0, node_to_fac[np.clip(src, 0, None)], -1)
    return dist.astype(np.float32), fac.astype(np.int64)


def access_file(derived: Path, variant: str, category: str) -> Path:
    """Path of ``access_<variant>_<category>.npz``."""
    return derived / f"access_{variant}_{category}.npz"


def ingest_access(session: Session, settings: BlizuSettings) -> dict[str, Any]:
    """``blizu ingest access``: snap facilities, run Dijkstra, save one .npz per variant/category."""
    manifest = Manifest(settings.derived_dir)
    graph = load_graph(manifest.path_of("graph"))
    facilities = load_facility_frame(session)
    if facilities.empty:
        raise RuntimeError(
            "no facilities in the database; run `blizu ingest facilities` and `gtfs` first"
        )
    today = datetime.now(UTC).date().isoformat()
    report: dict[str, Any] = {}
    dropped_rows: list[dict[str, Any]] = []
    with record_ingestion(session, SRC_GRAPH, "access arrays (scipy dijkstra)") as run:
        files: dict[str, str] = {}
        for category in CATEGORIES:
            sub = facilities[facilities["category"] == category]
            snap = snap_facilities(sub, graph)
            official = sub[sub["tier"] == "official"]
            official_dropped = (
                snap.dropped[snap.dropped["tier"] == "official"]
                if len(snap.dropped)
                else snap.dropped
            )
            report[category] = {
                "facilities": snap.total,
                "dropped": len(snap.dropped),
                "official": len(official),
                "official_dropped": len(official_dropped),
            }
            log.info("snap", category=category, **report[category])
            for r in snap.dropped.itertuples(index=False):
                dropped_rows.append(
                    {
                        "facility_id": r.id,
                        "category": r.category,
                        "name": r.name,
                        "source_id": r.source_id,
                        "tier": r.tier,
                        "nearest_node_m": r.nearest_node_m,
                    }
                )
            for variant in VARIANTS:
                dist, fac = nearest_facility_distances(graph, variant, snap)
                path = access_file(settings.derived_dir, variant, category)
                np.savez_compressed(path, distance_m=dist, facility_id=fac)
                files[f"{variant}_{category}"] = path.name
        run.rows = len(files)
        run.sha256 = (
            sha256_file(access_file(settings.derived_dir, "full", "prijevoz"))
            if (access_file(settings.derived_dir, "full", "prijevoz").exists())
            else None
        )
    dropped_path = settings.derived_dir / f"access_dropped_{today}.csv"
    with dropped_path.open("w", newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(
            fh,
            fieldnames=["facility_id", "category", "name", "source_id", "tier", "nearest_node_m"],
        )
        writer.writeheader()
        writer.writerows(dropped_rows)
    tot_official = sum(v["official"] for v in report.values())
    drop_official = sum(v["official_dropped"] for v in report.values())
    share = 1.0 - drop_official / tot_official if tot_official else None
    manifest.set(
        "access",
        date=today,
        files=files,
        per_category=report,
        official_snapped_share=share,
        dropped_csv=dropped_path.name,
        graph_sha256=manifest.get(
            "graph",
        )
        and manifest.get("graph")["sha256"],  # type: ignore[index]
    )
    log.info("official_snapped_share", share=share, dropped_total=len(dropped_rows))
    return report


def load_access_arrays(
    derived: Path, manifest: Manifest | None = None
) -> dict[tuple[str, str], tuple[np.ndarray, np.ndarray]]:
    """Load ``{(variant, category): (distance_m, facility_id)}`` as listed in the manifest."""
    manifest = manifest or Manifest(derived)
    entry = manifest.get("access")
    if not entry:
        raise KeyError("manifest has no 'access' entry; run `blizu ingest access`")
    out: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]] = {}
    for key, name in entry["files"].items():
        variant, category = key.split("_", 1)
        with np.load(derived / name, allow_pickle=False) as z:
            out[(variant, category)] = (z["distance_m"], z["facility_id"])
    return out
