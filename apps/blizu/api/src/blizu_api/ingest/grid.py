"""Population grid clipped to Grad Zagreb and per-cell mean walking minutes."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime

import geopandas as gpd
import numpy as np
import pandas as pd
import structlog
from pyproj import Transformer
from scipy.spatial import cKDTree
from shapely.geometry import mapping
from sqlalchemy import delete, insert, text
from sqlalchemy.orm import Session

from blizu_api.constants import (
    CATEGORIES,
    CRS_GRID,
    CRS_METRIC,
    CRS_WGS84,
    DIJKSTRA_LIMIT_M,
    PERSONAS,
    SRC_GRAPH,
)
from blizu_api.db import Cell, CellAccess
from blizu_api.ingest.access import load_access_arrays
from blizu_api.ingest.graph import GraphData, load_graph
from blizu_api.manifest import Manifest, sha256_file
from blizu_api.scoring import ScoringConfig, load_config, minutes
from blizu_api.settings import BlizuSettings
from opendata_core import http as http_mod
from opendata_core import popgrid
from opendata_core.provenance import record_ingestion

log = structlog.get_logger(__name__)

MIN_NODES_PER_CELL = 3
CELL_SIZE_M = 1000


def cell_ids_of(lon: np.ndarray, lat: np.ndarray) -> np.ndarray:
    """Eurostat 1 km GRD_ID of the cell containing each WGS84 point (SW-corner naming)."""
    tr = Transformer.from_crs(CRS_WGS84, CRS_GRID, always_xy=True)
    e, n = tr.transform(lon, lat)
    east = (np.floor(np.asarray(e) / CELL_SIZE_M) * CELL_SIZE_M).astype(np.int64)
    north = (np.floor(np.asarray(n) / CELL_SIZE_M) * CELL_SIZE_M).astype(np.int64)
    return np.array(
        [f"CRS3035RES{CELL_SIZE_M}mN{nn}E{ee}" for nn, ee in zip(north, east, strict=True)],
        dtype=object,
    )


def cell_mean_minutes(
    node_cell: np.ndarray,
    node_minutes: np.ndarray,
    cell_ids: list[str],
    cell_xy: np.ndarray,
    node_xy: np.ndarray,
    min_nodes: int = MIN_NODES_PER_CELL,
) -> pd.Series:
    """Mean minutes over the nodes of each cell; cells with < ``min_nodes`` nodes use the node
    nearest to the cell centroid instead.

    ``cell_xy`` / ``node_xy`` are in the same metric CRS. Returns a Series indexed by cell id.
    """
    df = pd.DataFrame({"cell": node_cell, "m": node_minutes})
    grouped = df.groupby("cell")["m"].agg(["mean", "count"])
    out = pd.Series(np.nan, index=pd.Index(cell_ids, name="grd_id"), dtype=float)
    have = grouped.index.intersection(out.index)
    out.loc[have] = grouped.loc[have, "mean"]
    few = [c for c in cell_ids if c not in grouped.index or grouped.loc[c, "count"] < min_nodes]
    if few:
        tree = cKDTree(node_xy)
        pos = pd.Series(range(len(cell_ids)), index=cell_ids)
        _, nearest = tree.query(cell_xy[pos.loc[few].to_numpy()], k=1)
        out.loc[few] = node_minutes[nearest]
    return out


def clip_cells_to_zagreb(session: Session, boundary_geojson: str) -> int:
    """Copy popgrid cells whose centroid lies inside the Zagreb boundary into ``cell`` (WGS84)."""
    session.execute(delete(CellAccess))
    session.execute(delete(Cell))
    session.execute(
        text(
            """
            insert into cell (grd_id, geom, pop_total, pop_u15, pop_65p)
            select p.grd_id, st_transform(p.geom, 4326), p.pop_total, p.pop_under15, p.pop_65plus
            from popgrid_cell p
            where st_intersects(p.centroid, st_setsrid(st_geomfromgeojson(:b), 4326))
            """
        ),
        {"b": boundary_geojson},
    )
    return int(session.execute(text("select count(*) from cell")).scalar_one())


def boundary_geojson(manifest: Manifest) -> str:
    """Geometry of Grad Zagreb (saved by the graph step) as a GeoJSON geometry string."""
    gdf = gpd.read_file(manifest.path_of("graph", "boundary"))
    return json.dumps(mapping(gdf.geometry.union_all()))


def compute_cell_access(
    graph: GraphData,
    arrays: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]],
    cells: pd.DataFrame,
    cfg: ScoringConfig,
) -> pd.DataFrame:
    """Rows ``grd_id, persona, category, mean_minutes`` for every cell."""
    node_cell = cell_ids_of(graph.lon, graph.lat)
    node_xy = np.column_stack([graph.x, graph.y])
    tr = Transformer.from_crs(CRS_WGS84, CRS_METRIC, always_xy=True)
    cx, cy = tr.transform(cells["lon"].to_numpy(), cells["lat"].to_numpy())
    cell_xy = np.column_stack([cx, cy])
    ids = cells["grd_id"].tolist()
    frames = []
    for persona_id in PERSONAS:
        persona = cfg.personas[persona_id]
        for category in CATEGORIES:
            dist, _ = arrays[(persona.graph, category)]
            capped = np.minimum(
                np.nan_to_num(dist.astype(float), posinf=DIJKSTRA_LIMIT_M), DIJKSTRA_LIMIT_M
            )
            node_minutes = minutes(capped, persona.speed_mps)
            series = cell_mean_minutes(node_cell, node_minutes, ids, cell_xy, node_xy)
            frames.append(
                pd.DataFrame(
                    {
                        "grd_id": series.index,
                        "persona": persona_id,
                        "category": category,
                        "mean_minutes": series.to_numpy(),
                    }
                )
            )
    return pd.concat(frames, ignore_index=True)


def ensure_popgrid(session: Session, settings: BlizuSettings) -> None:
    """Download the Eurostat package if needed and load Croatia into ``popgrid_cell``."""
    zip_path = settings.raw_dir / "Eurostat_Census-GRID_2021_V3.zip"
    modified = None
    with http_mod.make_client(settings) as client:
        head = client.head(popgrid.DOWNLOAD_URL)
        if head.headers.get("Last-Modified"):
            modified = parsedate_to_datetime(head.headers["Last-Modified"])
        expected = int(head.headers.get("Content-Length", "0"))
        if not zip_path.exists() or (expected and zip_path.stat().st_size != expected):
            log.info("downloading_eurostat_grid", mb=round(expected / 1e6))
            popgrid.download_popgrid(client, settings.raw_dir)
    sha = sha256_file(zip_path)
    result = popgrid.load_popgrid(session, zip_path, sha256=sha, source_last_modified=modified)
    log.info("popgrid_loaded", rows=result.rows, has_age_groups=result.has_age_groups)


def ingest_grid(session: Session, settings: BlizuSettings) -> int:
    """``blizu ingest grid``: Eurostat grid -> ``cell`` (Zagreb) -> ``cell_access``."""
    manifest = Manifest(settings.derived_dir)
    graph = load_graph(manifest.path_of("graph"))
    arrays = load_access_arrays(settings.derived_dir, manifest)
    cfg = load_config()

    ensure_popgrid(session, settings)
    n_cells = clip_cells_to_zagreb(session, boundary_geojson(manifest))
    session.commit()
    log.info("cells_in_zagreb", n=n_cells)

    cells = pd.DataFrame(
        session.execute(
            text(
                "select grd_id, st_x(st_centroid(geom)) as lon, st_y(st_centroid(geom)) as lat from cell"
            )
        )
        .mappings()
        .all()
    )
    with record_ingestion(session, SRC_GRAPH, "cell_access (mean minutes per 1 km cell)") as run:
        access = compute_cell_access(graph, arrays, cells, cfg)
        records = access.to_dict("records")
        for i in range(0, len(records), 10000):
            session.execute(insert(CellAccess), records[i : i + 10000])
        run.rows = len(records)
        run.sha256 = manifest.get("graph")["sha256"]  # type: ignore[index]
    manifest.set(
        "grid",
        date=datetime.now(UTC).date().isoformat(),
        cells=n_cells,
        cell_access_rows=len(access),
        has_age_groups=popgrid.popgrid_has_age_groups(session),
    )
    return n_cells
