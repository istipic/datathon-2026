"""Shared fixtures: the REAL 1 km OSM subgraph around Trg bana Jelacica (recorded 2026-11-03)."""

from __future__ import annotations

import ast
import json
import os
from pathlib import Path

import pandas as pd
import pytest
from shapely.geometry import shape

from blizu_api.constants import CATEGORIES, VARIANTS
from blizu_api.ingest.access import nearest_facility_distances, snap_facilities
from blizu_api.ingest.graph import GraphData, graph_from_edges
from blizu_api.ingest.grid import compute_cell_access
from blizu_api.scoring import load_config
from blizu_api.store import DataStore

FIXTURES = Path(__file__).parent / "fixtures"
DATE = "2026-11-03"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    skip_live = pytest.mark.skip(reason="live network test: set RUN_LIVE=1")
    skip_db = pytest.mark.skip(reason="needs PostGIS: set TEST_DATABASE_URL")
    for item in items:
        if "live" in item.keywords and os.environ.get("RUN_LIVE") != "1":
            item.add_marker(skip_live)
        if "db" in item.keywords and not os.environ.get("TEST_DATABASE_URL"):
            item.add_marker(skip_db)


def _maybe_list(value: object) -> object:
    """CSV stores OSM list tags like "['steps', 'footway']"; turn them back into lists."""
    if isinstance(value, str) and value.startswith("["):
        return ast.literal_eval(value)
    return None if isinstance(value, float) and pd.isna(value) else value


def load_subgraph_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    nodes = pd.read_csv(FIXTURES / "osm-graph" / f"{DATE}_nodes_trg_bana_jelacica_1km.csv")
    edges = pd.read_csv(FIXTURES / "osm-graph" / f"{DATE}_edges_trg_bana_jelacica_1km.csv")
    for col in ("highway", "wheelchair", "name"):
        if col in edges.columns:
            edges[col] = edges[col].map(_maybe_list)
    return nodes, edges


@pytest.fixture(scope="session")
def edges_frame() -> pd.DataFrame:
    return load_subgraph_frames()[1]


@pytest.fixture(scope="session")
def subgraph() -> GraphData:
    nodes, edges = load_subgraph_frames()
    return graph_from_edges(
        nodes["osmid"].to_numpy(), nodes["lon"].to_numpy(), nodes["lat"].to_numpy(), edges
    )


# ----------------------------------------------------------------------------- real-data store
STORE_DIR = FIXTURES / "store"
TRG = (45.81277, 15.97659)  # lat, lon: Nominatim "Trg bana Josipa Jelacica", recorded 2026-11-03


def load_real_facilities() -> pd.DataFrame:
    path = STORE_DIR / f"{DATE}_facilities_trg_bana_jelacica.json"
    return pd.DataFrame(json.loads(path.read_text(encoding="utf-8"))).set_index("id", drop=False)


def build_store(graph: GraphData, drop_category: str | None = None) -> DataStore:
    """DataStore from the real subgraph + real facilities/cells, using the production functions."""
    facilities = load_real_facilities()
    if drop_category:
        facilities = facilities[facilities["category"] != drop_category]
    arrays = {}
    for category in CATEGORIES:
        sub = facilities[facilities["category"] == category].reset_index(drop=True)
        snap = snap_facilities(sub, graph)
        for variant in VARIANTS:
            arrays[(variant, category)] = nearest_facility_distances(graph, variant, snap)
    cells_path = STORE_DIR / f"{DATE}_cells_trg_bana_jelacica.json"
    cells = pd.DataFrame(json.loads(cells_path.read_text(encoding="utf-8")))
    centroids = [shape(g).centroid for g in cells["geometry"]]
    cells["lon"] = [c.x for c in centroids]
    cells["lat"] = [c.y for c in centroids]
    cfg = load_config()
    access = compute_cell_access(graph, arrays, cells, cfg)
    sources_path = STORE_DIR / f"{DATE}_sources.json"
    sources = {s["id"]: s for s in json.loads(sources_path.read_text(encoding="utf-8"))["sources"]}
    return DataStore(
        cfg=cfg,
        graph=graph,
        arrays=arrays,
        facilities=facilities,
        cells=cells[["grd_id", "geometry", "pop_total", "pop_u15", "pop_65p"]],
        cell_access=access,
        boundary=None,
        sources=sources,
        has_age_groups=True,
    )


@pytest.fixture(scope="session")
def store(subgraph: GraphData) -> DataStore:
    return build_store(subgraph)
