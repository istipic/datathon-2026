"""OSM features from a Geofabrik extract (fallback when the public Overpass API is unavailable).

The result has the same shape as ``osmnx.features_from_place`` (GeoDataFrame indexed by
``(osm_type, osm_id)``, tag columns, WGS84 geometry), so :func:`osm_features_to_frame` handles both.
"""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import geopandas as gpd
import osmium
import pandas as pd
import structlog
from shapely import wkb
from shapely.geometry import Point, box
from shapely.geometry.base import BaseGeometry
from shapely.prepared import prep

from opendata_core import http as http_mod

log = structlog.get_logger(__name__)

GEOFABRIK_URL = "https://download.geofabrik.de/europe/croatia-latest.osm.pbf"
FALLBACK_BBOX = (15.70, 45.55, 16.30, 46.02)  # lon/lat box around Grad Zagreb

TAG_COLUMNS = (
    "name",
    "amenity",
    "shop",
    "leisure",
    "opening_hours",
    "wheelchair",
    "website",
    "addr:street",
    "addr:housenumber",
)
SCHOOL_NAMES = "_school_names"

_AMENITY = {
    "doctors": "lijecnik",
    "clinic": "lijecnik",
    "pharmacy": "ljekarna",
    "library": "knjiznica",
    "post_office": "posta",
    "school": SCHOOL_NAMES,
}
_SHOP = {"supermarket": "namirnice", "convenience": "namirnice"}


def category_of(tags: dict[str, str]) -> str | None:
    """Blizu category (or the school-name-hint bucket) an OSM feature belongs to."""
    if tags.get("amenity") in _AMENITY:
        return _AMENITY[tags["amenity"]]
    if tags.get("shop") in _SHOP:
        return _SHOP[tags["shop"]]
    if tags.get("leisure") == "park":
        return "park"
    return None


@dataclass(frozen=True)
class PbfInfo:
    """Provenance of the extract that was used."""

    path: Path
    url: str
    snapshot: datetime | None
    sha256: str


def download_extract(client: Any, raw_dir: Path, today: str) -> PbfInfo:
    """Download (or reuse) the Croatia extract; returns its path and snapshot time."""
    from blizu_api.manifest import sha256_file

    head = client.head(GEOFABRIK_URL)
    modified = head.headers.get("Last-Modified")
    expected = int(head.headers.get("Content-Length", "0"))
    path = raw_dir / f"{today}_croatia-latest.osm.pbf"
    if not path.exists() or (expected and path.stat().st_size != expected):
        log.info("downloading_geofabrik_extract", mb=round(expected / 1e6))
        http_mod.download_file(client, GEOFABRIK_URL, path)
    return PbfInfo(
        path=path,
        url=str(head.url),
        snapshot=parsedate_to_datetime(modified) if modified else None,
        sha256=sha256_file(path),
    )


def _iter_features(
    pbf: Path,
) -> Iterator[tuple[str, tuple[str, int], dict[str, str], BaseGeometry]]:
    fp = (
        osmium.FileProcessor(str(pbf))
        .with_locations()
        .with_areas()
        .with_filter(osmium.filter.KeyFilter("amenity", "shop", "leisure"))
    )
    factory = osmium.geom.WKBFactory()
    for obj in fp:
        if obj.is_node():
            tags = {t.k: t.v for t in obj.tags}
            category = category_of(tags)
            if category and obj.location.valid():
                yield category, ("node", obj.id), tags, Point(obj.location.lon, obj.location.lat)
        elif obj.is_area():
            tags = {t.k: t.v for t in obj.tags}
            category = category_of(tags)
            if category:
                geom = wkb.loads(factory.create_multipolygon(obj), hex=True)
                osm_type = "way" if obj.from_way() else "relation"
                yield category, (osm_type, obj.orig_id()), tags, geom


def extract_features(pbf: Path, boundary: BaseGeometry | None) -> dict[str, gpd.GeoDataFrame]:
    """Features per category (plus the school-name hints) inside ``boundary`` (or a Zagreb box)."""
    region = prep(boundary if boundary is not None else box(*FALLBACK_BBOX))
    rows: dict[str, list[dict[str, Any]]] = {}
    index: dict[str, list[tuple[str, int]]] = {}
    for category, key, tags, geom in _iter_features(pbf):
        anchor = geom if geom.geom_type == "Point" else geom.representative_point()
        if not region.contains(anchor):
            continue
        row: dict[str, Any] = {c: tags.get(c) for c in TAG_COLUMNS}
        row["geometry"] = geom
        rows.setdefault(category, []).append(row)
        index.setdefault(category, []).append(key)
    out: dict[str, gpd.GeoDataFrame] = {}
    for category, items in rows.items():
        idx = pd.MultiIndex.from_tuples(index[category], names=["element", "id"])
        out[category] = gpd.GeoDataFrame(items, index=idx, geometry="geometry", crs=4326)
    return out
