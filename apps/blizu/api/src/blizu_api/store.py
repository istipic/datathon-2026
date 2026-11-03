"""In-memory data used by the API: graph, access arrays, facilities, cells, boundary, source ages."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import structlog
from pyproj import Transformer
from scipy.spatial import cKDTree
from shapely.geometry import shape
from shapely.prepared import PreparedGeometry, prep
from sqlalchemy import text
from sqlalchemy.orm import Session

from blizu_api.constants import CATEGORIES, CRS_METRIC, CRS_WGS84, PERSONAS
from blizu_api.ingest.access import load_access_arrays, load_facility_frame
from blizu_api.ingest.graph import GraphData, load_graph
from blizu_api.ingest.grid import cell_ids_of
from blizu_api.manifest import Manifest
from blizu_api.scoring import ScoringConfig, load_config
from blizu_api.settings import BlizuSettings
from opendata_core.provenance import sources_summary

log = structlog.get_logger(__name__)

GROUP_COLUMNS = {"pop_total": "pop_total", "pop_u15": "pop_u15", "pop_65p": "pop_65p"}
FALLBACK_GROUP = "pop_total"
STREET_MAX_M = 150.0


@dataclass
class DataStore:
    """Everything the endpoints need, loaded once at start-up."""

    cfg: ScoringConfig
    graph: GraphData
    arrays: dict[tuple[str, str], tuple[np.ndarray, np.ndarray]]
    facilities: pd.DataFrame  # indexed by id
    cells: pd.DataFrame  # grd_id, geometry (GeoJSON dict), pop_total, pop_u15, pop_65p
    cell_access: pd.DataFrame  # grd_id, persona, category, mean_minutes
    boundary: PreparedGeometry | None
    sources: dict[str, dict[str, Any]]
    has_age_groups: bool
    manifest: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.tree = cKDTree(np.column_stack([self.graph.x, self.graph.y]))
        self._to_metric = Transformer.from_crs(CRS_WGS84, CRS_METRIC, always_xy=True)
        self.cells = self.cells.reset_index(drop=True)
        cell_index = {g: i for i, g in enumerate(self.cells["grd_id"])}
        node_cells = cell_ids_of(self.graph.lon, self.graph.lat)
        self.node_cell = np.array([cell_index.get(c, -1) for c in node_cells], dtype=np.int64)
        self.nodes_per_cell = np.bincount(
            self.node_cell[self.node_cell >= 0], minlength=len(self.cells)
        )
        named = np.flatnonzero(self.graph.street != "")
        self._named_nodes = named
        self._street_tree = (
            cKDTree(np.column_stack([self.graph.x[named], self.graph.y[named]]))
            if named.size
            else None
        )
        self._minutes: dict[tuple[str, str], np.ndarray] = {}
        for (persona, category), g in self.cell_access.groupby(["persona", "category"]):
            series = g.set_index("grd_id")["mean_minutes"].reindex(self.cells["grd_id"])
            self._minutes[(str(persona), str(category))] = series.to_numpy(dtype=float)
        self.categories_with_data = {
            c for c in CATEGORIES if (self.facilities["category"] == c).any()
        }

    def street_near(self, node: int, max_m: float = STREET_MAX_M) -> str | None:
        """Street name of ``node``, else of the nearest named node within ``max_m`` metres.

        Only ~12 % of OSM walking edges carry a name (sidewalks are separate unnamed footways).
        """
        own = str(self.graph.street[node])
        if own:
            return own
        if self._street_tree is None:
            return None
        dist, idx = self._street_tree.query([self.graph.x[node], self.graph.y[node]], k=1)
        return str(self.graph.street[self._named_nodes[idx]]) if dist <= max_m else None

    def dominant_source(self, category: str) -> str | None:
        """Source id that holds most facilities of a category."""
        sub = self.facilities[self.facilities["category"] == category]
        return None if sub.empty else str(sub["source_id"].value_counts().index[0])

    def default_tier(self, category: str) -> str:
        """Tier of the category's dominant source (used when no facility is within reach)."""
        sub = self.facilities[self.facilities["category"] == category]
        return "community" if sub.empty else str(sub["tier"].mode().iloc[0])

    def default_days(self, category: str) -> float | None:
        """Data age of the category's dominant source."""
        source = self.dominant_source(category)
        return None if source is None else self.source_days(source)

    # ------------------------------------------------------------------ geometry helpers
    def snap(self, lon: float, lat: float) -> tuple[int, float]:
        """Nearest graph node and its distance in metres."""
        x, y = self._to_metric.transform(lon, lat)
        dist, idx = self.tree.query([x, y], k=1)
        return int(idx), float(dist)

    def inside_boundary(self, lon: float, lat: float) -> bool:
        """True if the point lies within Grad Zagreb (always True when no boundary is loaded)."""
        if self.boundary is None:
            return True
        from shapely.geometry import Point

        return bool(self.boundary.contains(Point(lon, lat)))

    # ------------------------------------------------------------------ facility / source info
    def facility(self, fid: int) -> dict[str, Any] | None:
        """Facility record by id or None."""
        if fid < 0 or fid not in self.facilities.index:
            return None
        row = self.facilities.loc[fid]
        return {
            "id": int(fid),
            "name": row["name"],
            "address": row["address"],
            "lon": float(row["lon"]),
            "lat": float(row["lat"]),
            "source_id": row["source_id"],
            "tier": row["tier"],
            "category": row["category"],
        }

    def source_days(self, source_id: str) -> float | None:
        """Age of the data of a source in days (freshness_days), if known."""
        value = self.sources.get(source_id, {}).get("freshness_days")
        return None if value is None else float(value)

    # ------------------------------------------------------------------ population / cells
    def group_for(self, category: str) -> tuple[str, str]:
        """(population column, hr label) for a category; falls back to total population."""
        group = self.cfg.categories[category].group
        if group != FALLBACK_GROUP and not self.has_age_groups:
            group = FALLBACK_GROUP
        return group, self.cfg.group_labels[group]

    def group_population(self, category: str) -> tuple[np.ndarray, str, str]:
        """Population of the category's target group per cell (NaN -> 0), column name, label."""
        column, label = self.group_for(category)
        values = pd.to_numeric(self.cells[column], errors="coerce").fillna(0).to_numpy(dtype=float)
        return values, column, label

    def cell_minutes(self, persona: str, category: str) -> np.ndarray:
        """Mean walking minutes per cell (aligned with ``cells``); NaN where missing."""
        return self._minutes.get((persona, category), np.full(len(self.cells), np.nan, dtype=float))

    def distance_array(self, persona: str, category: str) -> tuple[np.ndarray, np.ndarray]:
        """Per-node network distance (m) and nearest facility id for the persona's graph variant."""
        variant = self.cfg.personas[persona].graph
        return self.arrays[(variant, category)]


def load_boundary(derived: Path, manifest: Manifest) -> PreparedGeometry | None:
    """Grad Zagreb polygon saved by the graph step."""
    entry = manifest.get("graph") or {}
    name = entry.get("boundary")
    if not name:
        return None
    data = json.loads((derived / name).read_text(encoding="utf-8"))
    geoms = [shape(f["geometry"]) for f in data["features"]]
    from shapely.ops import unary_union

    return prep(unary_union(geoms))


def load_store(session: Session, settings: BlizuSettings) -> DataStore:
    """Build the :class:`DataStore` from the manifest files and the database."""
    manifest = Manifest(settings.derived_dir)
    graph = load_graph(manifest.path_of("graph"))
    arrays = load_access_arrays(settings.derived_dir, manifest)
    facilities = load_facility_frame(session).set_index("id", drop=False)
    cells_raw = session.execute(
        text(
            "select grd_id, st_asgeojson(geom, 6) as geojson, pop_total, pop_u15, pop_65p from cell order by grd_id"
        )
    ).mappings()
    cells = pd.DataFrame(
        [
            {
                "grd_id": r["grd_id"],
                "geometry": json.loads(r["geojson"]),
                "pop_total": r["pop_total"],
                "pop_u15": r["pop_u15"],
                "pop_65p": r["pop_65p"],
            }
            for r in cells_raw
        ]
    )
    access = pd.DataFrame(
        session.execute(text("select grd_id, persona, category, mean_minutes from cell_access"))
        .mappings()
        .all()
    )
    summary = {s["id"]: s for s in sources_summary(session)}
    has_age = bool(cells["pop_65p"].notna().any()) if len(cells) else False
    store = DataStore(
        cfg=load_config(),
        graph=graph,
        arrays=arrays,
        facilities=facilities,
        cells=cells,
        cell_access=access,
        boundary=load_boundary(settings.derived_dir, manifest),
        sources=summary,
        has_age_groups=has_age,
        manifest=manifest.read(),
    )
    log.info(
        "store_loaded",
        nodes=graph.n_nodes,
        facilities=len(facilities),
        cells=len(cells),
        has_age_groups=has_age,
        personas=len(PERSONAS),
    )
    return store
