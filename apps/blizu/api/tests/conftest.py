"""Shared fixtures: the REAL 1 km OSM subgraph around Trg bana Jelacica (recorded 2026-11-03)."""

from __future__ import annotations

import ast
import os
from pathlib import Path

import pandas as pd
import pytest

from blizu_api.ingest.graph import GraphData, graph_from_edges

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
