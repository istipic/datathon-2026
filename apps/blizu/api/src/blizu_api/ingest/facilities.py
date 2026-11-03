"""Facilities: official kindergartens/schools + OSM categories, deduplicated (official wins)."""

from __future__ import annotations

import io
import json
from contextlib import ExitStack
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import structlog
from pyproj import Transformer
from scipy.spatial import cKDTree
from sqlalchemy import delete, insert
from sqlalchemy.orm import Session

from blizu_api.constants import (
    CRS_METRIC,
    CRS_WGS84,
    PLACE,
    SRC_GTFS,
    SRC_OSM,
    SRC_SKOLE,
    SRC_VRTICI,
)
from blizu_api.db import Facility
from blizu_api.ingest.overpass import with_overpass_retry
from blizu_api.manifest import Manifest, sha256_file
from blizu_api.settings import BlizuSettings
from opendata_core import http as http_mod
from opendata_core.ckan import CkanClient, CkanError
from opendata_core.provenance import record_ingestion

log = structlog.get_logger(__name__)

VRTICI_PACKAGE = "geoportal-djecji-vrtici"
VRTICI_RESOURCE_ID = "75200bbf-08b0-4077-8185-f3d1abf907b0"
SKOLE_PACKAGE = "djeji-vrtii-osnovne-i-srednje-kole-grada-zagreba-inspire"
SKOLE_TYPENAME = "us-govserv:GovernmentalService"
PRIMARY_EDUCATION = "primaryEducation"
EXCLUDED_KINDERGARTEN_TYPES = {"Vrtić u bolnici", "Posebna ustanova"}
DEDUPE_RADIUS_M = 50.0
NAME_HINT_RADIUS_M = 50.0

COLUMNS = [
    "category",
    "name",
    "address",
    "lon",
    "lat",
    "source_id",
    "tier",
    "source_record_id",
    "attrs",
]

# OSM tag filters per category (spec): value lists are OR-ed.
OSM_TAGS: dict[str, dict[str, Any]] = {
    "lijecnik": {"amenity": ["doctors", "clinic"]},
    "ljekarna": {"amenity": "pharmacy"},
    "knjiznica": {"amenity": "library"},
    "posta": {"amenity": "post_office"},
    "park": {"leisure": "park"},
    "namirnice": {"shop": ["supermarket", "convenience"]},
}
# Used ONLY to attach names to official records that have none (never inserted as facilities).
OSM_NAME_HINT_TAGS: dict[str, Any] = {"amenity": ["school"]}


def _clean(value: Any) -> str | None:
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    text = str(value).strip()
    return text or None


# ----------------------------------------------------------------------------- official parsers


def parse_vrtici(csv_text: str) -> pd.DataFrame:
    """Parse the Zagreb kindergarten CSV (columns X=lon, Y=lat, OBJECTID, naziv, adresa, ...)."""
    df = pd.read_csv(io.StringIO(csv_text.lstrip("﻿")))
    df = df[~df["vr_vrtica"].isin(EXCLUDED_KINDERGARTEN_TYPES)]
    if not (df["X"].between(15.5, 16.5).all() and df["Y"].between(45.5, 46.1).all()):
        raise ValueError("kindergarten coordinates are not WGS84 lon/lat for Zagreb")
    attr_cols = [
        "grad_cetvr",
        "vr_vrtica",
        "tip_vrtica",
        "telefon",
        "web",
        "gradjevina",
        "strani_jez",
    ]
    out = pd.DataFrame(
        {
            "category": "vrtic",
            "name": df["naziv"].map(_clean),
            "address": df["adresa"].map(_clean),
            "lon": df["X"].astype(float),
            "lat": df["Y"].astype(float),
            "source_id": SRC_VRTICI,
            "tier": "official",
            "source_record_id": df["OBJECTID"].astype(str),
            "attrs": [
                {k: _clean(row[k]) for k in attr_cols if k in df.columns}
                for _, row in df.iterrows()
            ],
        }
    )
    return out[COLUMNS].reset_index(drop=True)


def parse_skole(geojson: dict[str, Any]) -> pd.DataFrame:
    """Primary schools from the INSPIRE GovernmentalService GeoJSON (no names in the source)."""
    rows = []
    for f in geojson["features"]:
        props = f["properties"]
        service = props["serviceType"]["href"].rsplit("/", 1)[-1]
        if service != PRIMARY_EDUCATION or not f.get("geometry"):
            continue
        lon, lat = f["geometry"]["coordinates"][:2]
        local_id = props["inspireId"]["Identifier"]["localId"]
        rows.append(
            {
                "category": "skola",
                "name": None,
                "address": None,
                "lon": float(lon),
                "lat": float(lat),
                "source_id": SRC_SKOLE,
                "tier": "official",
                "source_record_id": str(local_id),
                "attrs": {"service_type": service, "inspire_id": f["id"]},
            }
        )
    return pd.DataFrame(rows, columns=COLUMNS)


# ----------------------------------------------------------------------------- OSM


def _address(row: pd.Series) -> str | None:
    street = _clean(row.get("addr:street"))
    number = _clean(row.get("addr:housenumber"))
    if street and number:
        return f"{street} {number}"
    return street


def park_access_points(geom: Any, max_boundary: int = 4) -> list[tuple[float, float]]:
    """Centroid plus up to ``max_boundary`` evenly spaced boundary points of a park polygon.

    ``geom`` must be in a projected CRS; points are returned in the same CRS.
    """
    points = [geom.representative_point()]
    boundary = geom.boundary
    parts = list(boundary.geoms) if hasattr(boundary, "geoms") else [boundary]
    parts = [p for p in parts if p.length > 0]
    if parts:
        ring = max(parts, key=lambda p: p.length)
        for i in range(max_boundary):
            points.append(ring.interpolate((i + 0.25) / max_boundary, normalized=True))
    return [(p.x, p.y) for p in points]


def osm_features_to_frame(gdf: Any, category: str) -> pd.DataFrame:
    """Convert an osmnx features GeoDataFrame to the facility frame (centroids, park access points)."""
    if gdf.empty:
        return pd.DataFrame(columns=COLUMNS)
    metric = gdf.to_crs(CRS_METRIC)
    back = Transformer.from_crs(CRS_METRIC, CRS_WGS84, always_xy=True)
    rows = []
    for (osm_type, osm_id), row in metric.iterrows():
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        rep = geom if geom.geom_type == "Point" else geom.representative_point()
        lon, lat = back.transform(rep.x, rep.y)
        attrs: dict[str, Any] = {"osm_url": f"https://www.openstreetmap.org/{osm_type}/{osm_id}"}
        for key in ("amenity", "shop", "leisure", "opening_hours", "wheelchair", "website"):
            if key in row.index and _clean(row[key]):
                attrs[key] = _clean(row[key])
        if category == "park" and geom.geom_type in ("Polygon", "MultiPolygon"):
            pts = park_access_points(geom)
            attrs["access_points"] = [list(back.transform(x, y)) for x, y in pts]
            attrs["area_m2"] = round(float(geom.area))
        rows.append(
            {
                "category": category,
                "name": _clean(row.get("name")),
                "address": _address(row),
                "lon": lon,
                "lat": lat,
                "source_id": SRC_OSM,
                "tier": "community",
                "source_record_id": f"{osm_type}/{osm_id}",
                "attrs": attrs,
            }
        )
    return pd.DataFrame(rows, columns=COLUMNS)


# ----------------------------------------------------------------------------- dedupe


def _xy(df: pd.DataFrame) -> np.ndarray:
    tr = Transformer.from_crs(CRS_WGS84, CRS_METRIC, always_xy=True)
    x, y = tr.transform(df["lon"].to_numpy(float), df["lat"].to_numpy(float))
    return np.column_stack([x, y])


def dedupe_official_vs_osm(
    df: pd.DataFrame, radius_m: float = DEDUPE_RADIUS_M
) -> tuple[pd.DataFrame, int]:
    """Drop community (OSM) rows that lie within ``radius_m`` of an official row of the same category.

    Returns ``(deduplicated frame, number of dropped rows)``. Official rows are never dropped.
    """
    keep = np.ones(len(df), dtype=bool)
    df = df.reset_index(drop=True)
    for category, idx in df.groupby("category").groups.items():
        sub = df.loc[idx]
        official = sub[sub["tier"] == "official"]
        community = sub[sub["tier"] != "official"]
        if official.empty or community.empty:
            continue
        tree = cKDTree(_xy(official))
        dist, _ = tree.query(_xy(community), k=1)
        keep[community.index[dist <= radius_m]] = False
        log.info("dedupe", category=category, dropped=int((dist <= radius_m).sum()))
    return df[keep].reset_index(drop=True), int((~keep).sum())


def attach_name_hints(
    official: pd.DataFrame, hints: pd.DataFrame, radius_m: float = NAME_HINT_RADIUS_M
) -> tuple[pd.DataFrame, int]:
    """Give nameless official rows the name of the nearest OSM hint within ``radius_m``.

    The origin is recorded in ``attrs['name_source'] = 'osm'`` (ODbL attribution applies).
    """
    official = official.copy()
    hints = hints[hints["name"].notna()].reset_index(drop=True)
    if official.empty or hints.empty:
        return official, 0
    tree = cKDTree(_xy(hints))
    dist, idx = tree.query(_xy(official), k=1)
    n = 0
    names = official["name"].tolist()
    attrs = [dict(a) for a in official["attrs"]]
    for i, (d, j) in enumerate(zip(dist, idx, strict=True)):
        if names[i] is None and d <= radius_m:
            names[i] = hints.loc[j, "name"]
            attrs[i]["name_source"] = "osm"
            attrs[i]["name_hint_distance_m"] = round(float(d), 1)
            n += 1
    official["name"] = names
    official["attrs"] = attrs
    return official, n


# ----------------------------------------------------------------------------- download


def _ckan_resource(ckan: CkanClient, resource_id: str) -> dict[str, Any]:
    try:
        return ckan.resource_show(resource_id)
    except CkanError as exc:  # pragma: no cover - network
        raise RuntimeError(f"cannot read CKAN resource {resource_id}: {exc}") from exc


def _parse_ts(value: str | None) -> datetime | None:
    if not value:
        return None
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def download_vrtici(
    ckan: CkanClient, raw_dir: Path, today: str
) -> tuple[Path, str, dict[str, Any]]:
    """Download the kindergarten CSV (resource id fixed by the task); returns path, sha, resource."""
    res = _ckan_resource(ckan, VRTICI_RESOURCE_ID)
    path, sha = ckan.download(res["url"], raw_dir / f"{today}_zg-vrtici.csv")
    return path, sha, res


def download_skole(
    ckan: CkanClient, client: Any, raw_dir: Path, today: str
) -> tuple[Path, str, str]:
    """Fetch primary/secondary/early-childhood points from the INSPIRE WFS as GeoJSON."""
    pkg = ckan.package_show(SKOLE_PACKAGE)
    wfs = next(r for r in pkg["resources"] if str(r.get("format", "")).upper() == "WFS")
    base = wfs["url"].split("?", 1)[0]
    params = {
        "SERVICE": "WFS",
        "VERSION": "2.0.0",
        "REQUEST": "GetFeature",
        "TYPENAMES": SKOLE_TYPENAME,
        "OUTPUTFORMAT": "application/geo+json",
        "SRSNAME": "urn:ogc:def:crs:EPSG::4326",
    }
    fetched = http_mod.fetch(client, "GET", base, params=params)
    path = raw_dir / f"{today}_zg-skole_wfs.geojson"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(fetched.content)
    return path, sha256_file(path), str(fetched.url)


def download_osm_features(settings: BlizuSettings) -> dict[str, pd.DataFrame]:
    """features_from_place per category (+ school names used only as hints)."""
    import osmnx as ox

    ox.settings.http_user_agent = f"blizu/0.1 (+mailto:{settings.contact_email}) datathon-2026"
    ox.settings.requests_timeout = 180  # feature queries are small; fail fast and retry
    ox.settings.cache_folder = str(settings.data_dir / "cache" / "osmnx")
    ox.settings.log_console = False
    out: dict[str, pd.DataFrame] = {}

    def set_endpoint(url: str) -> None:
        ox.settings.overpass_url = url

    for category, tags in OSM_TAGS.items():
        gdf = with_overpass_retry(
            f"features_{category}", lambda t=tags: ox.features_from_place(PLACE, t), set_endpoint
        )
        out[category] = osm_features_to_frame(gdf, category)
        log.info("osm_features", category=category, n=len(out[category]))
    hints = with_overpass_retry(
        "features_school_names",
        lambda: ox.features_from_place(PLACE, OSM_NAME_HINT_TAGS),
        set_endpoint,
    )
    out["_school_names"] = osm_features_to_frame(hints, "skola")
    return out


# ----------------------------------------------------------------------------- orchestration


def ingest_facilities(session: Session, settings: BlizuSettings) -> dict[str, int]:
    """``blizu ingest facilities``: download, parse, dedupe and load. Returns counts per source."""
    today = datetime.now(UTC).date().isoformat()
    raw_dir = settings.raw_dir
    with http_mod.make_client(settings) as client:
        ckan = CkanClient(settings, client=client)
        with ExitStack() as stack:
            run_v = stack.enter_context(
                record_ingestion(session, SRC_VRTICI, "CKAN geoportal-djecji-vrtici")
            )
            run_s = stack.enter_context(
                record_ingestion(session, SRC_SKOLE, "INSPIRE WFS (CKAN djeji-vrtii-...)")
            )
            run_o = stack.enter_context(
                record_ingestion(session, SRC_OSM, "Overpass features_from_place")
            )

            v_path, v_sha, v_res = download_vrtici(ckan, raw_dir, today)
            run_v.sha256 = v_sha
            run_v.retrieved_url = v_res["url"]
            run_v.source_last_modified = _parse_ts(v_res.get("last_modified"))
            vrtici = parse_vrtici(v_path.read_text(encoding="utf-8"))

            s_path, s_sha, s_url = download_skole(ckan, client, raw_dir, today)
            run_s.sha256 = s_sha
            run_s.retrieved_url = s_url
            run_s.source_last_modified = datetime.now(
                UTC
            )  # live service: no publication date in the data
            skole = parse_skole(json.loads(s_path.read_text(encoding="utf-8")))

            osm = download_osm_features(settings)
            run_o.source_last_modified = datetime.now(UTC)
            hints = osm.pop("_school_names")
            skole, named = attach_name_hints(skole, hints)
            log.info("school_names_from_osm", named=named, total=len(skole))

            frame = pd.concat([vrtici, skole, *osm.values()], ignore_index=True)
            frame, dropped = dedupe_official_vs_osm(frame)
            log.info("facilities_total", n=len(frame), dropped_osm_duplicates=dropped)

            session.execute(
                delete(Facility).where(Facility.source_id.in_([SRC_VRTICI, SRC_SKOLE, SRC_OSM]))
            )
            records = [
                {
                    "category": r.category,
                    "name": r.name,
                    "address": r.address,
                    "geom": f"SRID=4326;POINT({r.lon:.7f} {r.lat:.7f})",
                    "source_id": r.source_id,
                    "tier": r.tier,
                    "source_record_id": r.source_record_id,
                    "attrs": r.attrs,
                }
                for r in frame.itertuples(index=False)
            ]
            for i in range(0, len(records), 5000):
                session.execute(insert(Facility), records[i : i + 5000])
            counts = frame.groupby("source_id").size().to_dict()
            run_v.rows = int(counts.get(SRC_VRTICI, 0))
            run_s.rows = int(counts.get(SRC_SKOLE, 0))
            run_o.rows = int(counts.get(SRC_OSM, 0))
    Manifest(settings.derived_dir).set(
        "facilities",
        date=today,
        counts={k: int(v) for k, v in counts.items()},
        dropped_osm_duplicates=dropped,
    )
    return {k: int(v) for k, v in counts.items()} | {SRC_GTFS: 0}
