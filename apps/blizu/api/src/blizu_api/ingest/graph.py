"""Walking graph: OSM download -> two undirected scipy CSR graphs (full, wheelchair)."""

from __future__ import annotations

import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import scipy.sparse as sp
import structlog
from pyproj import Transformer
from sqlalchemy.orm import Session

from blizu_api.constants import CRS_METRIC, CRS_WGS84, PLACE, SRC_GRAPH, SRC_OSM
from blizu_api.ingest.overpass import with_overpass_retry
from blizu_api.ingest.sources import register_graph_sources
from blizu_api.manifest import Manifest, sha256_file
from blizu_api.settings import BlizuSettings
from opendata_core.provenance import record_ingestion

log = structlog.get_logger(__name__)

OVERPASS_URL = "https://overpass-api.de/api"


@dataclass
class GraphData:
    """In-memory walking graph (both variants share the node set)."""

    osmid: np.ndarray
    x: np.ndarray  # EPSG:3765 easting (m)
    y: np.ndarray  # EPSG:3765 northing (m)
    lon: np.ndarray
    lat: np.ndarray
    street: np.ndarray  # '<U..' street name of an incident edge ('' if none)
    full: sp.csr_matrix
    wheelchair: sp.csr_matrix

    def variant(self, name: str) -> sp.csr_matrix:
        """CSR matrix of variant ``full`` or ``wheelchair``."""
        return self.full if name == "full" else self.wheelchair

    @property
    def n_nodes(self) -> int:
        """Number of nodes."""
        return int(len(self.osmid))


def _as_list(value: Any) -> list[str]:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return []
    if isinstance(value, list | tuple | set):
        return [str(v) for v in value]
    return [str(value)]


def is_wheelchair_blocked(highway: Any, wheelchair: Any) -> bool:
    """True for edges a wheelchair user cannot use: highway=steps or wheelchair=no."""
    return "steps" in _as_list(highway) or "no" in _as_list(wheelchair)


def undirected_csr(u: np.ndarray, v: np.ndarray, length: np.ndarray, n: int) -> sp.csr_matrix:
    """Symmetric CSR graph; parallel edges keep the shortest length; self-loops dropped."""
    keep = u != v
    a = np.concatenate([u[keep], v[keep]])
    b = np.concatenate([v[keep], u[keep]])
    w = np.concatenate([length[keep], length[keep]])
    df = pd.DataFrame({"a": a, "b": b, "w": w}).groupby(["a", "b"], as_index=False)["w"].min()
    return sp.csr_matrix(
        (df["w"].to_numpy(float), (df["a"].to_numpy(), df["b"].to_numpy())), shape=(n, n)
    )


def graph_from_edges(
    node_ids: np.ndarray,
    lon: np.ndarray,
    lat: np.ndarray,
    edges: pd.DataFrame,
) -> GraphData:
    """Build :class:`GraphData` from nodes and an edge table.

    ``edges`` needs columns ``u, v`` (OSM node ids), ``length`` (m) and optionally ``highway``,
    ``wheelchair``, ``name``.
    """
    index = pd.Series(np.arange(len(node_ids)), index=node_ids)
    u = index.loc[edges["u"].to_numpy()].to_numpy()
    v = index.loc[edges["v"].to_numpy()].to_numpy()
    length = edges["length"].to_numpy(float)
    blocked = np.fromiter(
        (
            is_wheelchair_blocked(h, w)
            for h, w in zip(
                edges.get("highway", pd.Series([None] * len(edges))),
                edges.get("wheelchair", pd.Series([None] * len(edges))),
                strict=True,
            )
        ),
        dtype=bool,
        count=len(edges),
    )
    n = len(node_ids)
    full = undirected_csr(u, v, length, n)
    wheel = undirected_csr(u[~blocked], v[~blocked], length[~blocked], n)

    street = np.full(n, "", dtype=object)
    if "name" in edges.columns:
        names = edges["name"].map(lambda x: (_as_list(x) or [""])[0])
        named = pd.DataFrame({"n": np.concatenate([u, v]), "name": np.concatenate([names, names])})
        named = named[named["name"] != ""]
        if len(named):
            top = named.groupby("n")["name"].agg(lambda s: s.value_counts().index[0])
            street[top.index.to_numpy()] = top.to_numpy()

    tr = Transformer.from_crs(CRS_WGS84, CRS_METRIC, always_xy=True)
    x, y = tr.transform(lon, lat)
    return GraphData(
        osmid=np.asarray(node_ids, dtype=np.int64),
        x=np.asarray(x, dtype=float),
        y=np.asarray(y, dtype=float),
        lon=np.asarray(lon, dtype=float),
        lat=np.asarray(lat, dtype=float),
        street=street.astype(str),
        full=full,
        wheelchair=wheel,
    )


def save_graph(g: GraphData, path: Path) -> None:
    """Write nodes and both CSR matrices to one compressed ``.npz``."""
    path.parent.mkdir(parents=True, exist_ok=True)
    arrays: dict[str, np.ndarray] = {
        "osmid": g.osmid,
        "x": g.x,
        "y": g.y,
        "lon": g.lon,
        "lat": g.lat,
        "street": g.street,
    }
    for name in ("full", "wheelchair"):
        m = g.variant(name)
        arrays[f"{name}_data"] = m.data
        arrays[f"{name}_indices"] = m.indices
        arrays[f"{name}_indptr"] = m.indptr
        arrays[f"{name}_shape"] = np.array(m.shape)
    np.savez_compressed(path, **arrays)


def load_graph(path: Path) -> GraphData:
    """Read a graph written by :func:`save_graph`."""
    with np.load(path, allow_pickle=False) as z:

        def csr(name: str) -> sp.csr_matrix:
            return sp.csr_matrix(
                (z[f"{name}_data"], z[f"{name}_indices"], z[f"{name}_indptr"]),
                shape=tuple(int(s) for s in z[f"{name}_shape"]),
            )

        return GraphData(
            osmid=z["osmid"],
            x=z["x"],
            y=z["y"],
            lon=z["lon"],
            lat=z["lat"],
            street=z["street"],
            full=csr("full"),
            wheelchair=csr("wheelchair"),
        )


def fetch_boundary(settings: BlizuSettings, boundary_path: Path) -> Any | None:
    """Polygon of Grad Zagreb from Nominatim (via osmnx), saved as GeoJSON; None if unavailable."""
    import osmnx as ox

    ox.settings.http_user_agent = f"blizu/0.1 (+mailto:{settings.contact_email}) datathon-2026"
    ox.settings.cache_folder = str(settings.data_dir / "cache" / "osmnx")
    ox.settings.log_console = False
    try:
        boundary = ox.geocode_to_gdf(PLACE)  # Nominatim, cached by osmnx
    except Exception as exc:
        log.warning("boundary_unavailable", error=str(exc)[:200])
        return None
    boundary_path.parent.mkdir(parents=True, exist_ok=True)
    boundary[["geometry"]].to_file(boundary_path, driver="GeoJSON")
    return boundary.geometry.union_all()


def download_osm_graph(
    settings: BlizuSettings,
    graphml_path: Path,
    boundary_path: Path,
    max_attempts: int = 10,
    timeout_s: int = 600,
) -> GraphData:
    """Download the walking network of Grad Zagreb with osmnx and convert it."""
    import osmnx as ox

    ox.settings.http_user_agent = f"blizu/0.1 (+mailto:{settings.contact_email}) datathon-2026"
    ox.settings.requests_timeout = timeout_s
    ox.settings.cache_folder = str(settings.data_dir / "cache" / "osmnx")
    ox.settings.log_console = False
    ox.settings.useful_tags_way = sorted({*ox.settings.useful_tags_way, "wheelchair", "name"})

    t0 = time.time()

    def set_endpoint(url: str) -> None:
        ox.settings.overpass_url = url

    g = with_overpass_retry(
        "graph_from_place",
        lambda: ox.graph_from_place(PLACE, network_type="walk", retain_all=False),
        set_endpoint,
        max_attempts=max_attempts,
    )
    log.info(
        "osm_graph_downloaded",
        nodes=g.number_of_nodes(),
        edges=g.number_of_edges(),
        s=round(time.time() - t0),
    )
    ox.save_graphml(g, graphml_path)

    boundary = ox.geocode_to_gdf(PLACE)  # Nominatim, cached by osmnx
    boundary_path.parent.mkdir(parents=True, exist_ok=True)
    boundary[["geometry"]].to_file(boundary_path, driver="GeoJSON")

    nodes, edges = ox.graph_to_gdfs(g)
    edges = edges.reset_index()  # u, v, key
    return graph_from_edges(
        nodes.index.to_numpy(),
        nodes["x"].to_numpy(),
        nodes["y"].to_numpy(),
        pd.DataFrame(edges.drop(columns="geometry")),
    )


def graph_from_geofabrik(
    settings: BlizuSettings, boundary_path: Path, today: str, run: Any
) -> GraphData:
    """Build the graph from the Geofabrik Croatia extract and record its provenance on ``run``."""
    from blizu_api.ingest import osm_pbf
    from blizu_api.ingest.graph_pbf import graph_from_extract, region_or_box
    from opendata_core import http as http_mod

    with http_mod.make_client(settings) as client:
        info = osm_pbf.download_extract(client, settings.raw_dir, today)
    region = region_or_box(fetch_boundary(settings, boundary_path))
    run.retrieved_url = info.url
    run.sha256 = info.sha256
    run.source_last_modified = info.snapshot
    return graph_from_extract(info.path, region)


def ingest_graph(session: Session, settings: BlizuSettings) -> GraphData:
    """``blizu ingest graph``: download, build, save, record provenance (osm + derived graph)."""
    today = datetime.now(UTC).date().isoformat()
    derived = settings.derived_dir
    derived.mkdir(parents=True, exist_ok=True)
    register_graph_sources(session)
    session.commit()

    graphml = derived / f"osm-zagreb-walk_{today}.graphml"
    boundary = derived / f"zagreb-boundary_{today}.geojson"
    mode = settings.osm_feature_source
    via = "overpass"
    with record_ingestion(
        session, SRC_OSM, f"{OVERPASS_URL} (osmnx graph_from_place '{PLACE}')"
    ) as run:
        graph: GraphData | None = None
        if mode in ("auto", "overpass"):
            try:
                # auto: one attempt (3 min budget), then the extract; overpass: be patient
                graph = download_osm_graph(
                    settings,
                    graphml,
                    boundary,
                    max_attempts=1 if mode == "auto" else 10,
                    timeout_s=180 if mode == "auto" else 600,
                )
                run.sha256 = sha256_file(graphml)
                run.source_last_modified = datetime.now(UTC)  # continuously updated: extract time
            except Exception as exc:
                if mode == "overpass":
                    raise
                log.warning(
                    "overpass_unavailable_building_graph_from_geofabrik", error=str(exc)[:200]
                )
        if graph is None:
            via = "geofabrik"
            graph = graph_from_geofabrik(settings, boundary, today, run)
            graphml = None  # type: ignore[assignment]
        run.rows = graph.n_nodes

    npz = derived / f"graph_{today}.npz"
    with record_ingestion(session, SRC_GRAPH, str(npz.name)) as run:
        save_graph(graph, npz)
        run.rows = graph.n_nodes
        run.sha256 = sha256_file(npz)
        run.source_last_modified = datetime.now(UTC)
    Manifest(derived).set(
        "graph",
        file=npz.name,
        sha256=run.sha256,
        date=today,
        nodes=graph.n_nodes,
        edges_full=int(graph.full.nnz // 2),
        edges_wheelchair=int(graph.wheelchair.nnz // 2),
        graphml=graphml.name if graphml else None,
        boundary=boundary.name if boundary.exists() else None,
        via=via,
    )
    log.info("graph_saved", file=npz.name, nodes=graph.n_nodes)
    return graph
