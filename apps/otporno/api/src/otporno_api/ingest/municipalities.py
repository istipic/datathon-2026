"""Municipality boundaries: GISCO LAU 2024, Croatia only."""

from __future__ import annotations

import json
from typing import Any

import geopandas as gpd
import structlog
from shapely.geometry import MultiPolygon, Polygon
from sqlalchemy import text
from sqlalchemy.orm import Session

from opendata_core import http as http_mod
from opendata_core.provenance import record_ingestion
from otporno_api.constants import SRC_LAU
from otporno_api.settings import OtpornoSettings

log = structlog.get_logger(__name__)


def as_multipolygon(geom: Any) -> MultiPolygon:
    """Shapely geometry -> MultiPolygon (the column type)."""
    if isinstance(geom, Polygon):
        return MultiPolygon([geom])
    if isinstance(geom, MultiPolygon):
        return geom
    polys = [g for g in getattr(geom, "geoms", []) if isinstance(g, Polygon)]
    if not polys:
        raise ValueError(f"unsupported geometry {geom.geom_type}")
    return MultiPolygon(polys)


def read_croatia(path: Any) -> gpd.GeoDataFrame:
    """Croatian LAUs from the GISCO file (``CNTR_CODE = 'HR'``) in EPSG:4326."""
    gdf = gpd.read_file(path, where="CNTR_CODE = 'HR'")
    if gdf.empty:
        raise ValueError("no Croatian LAU found (CNTR_CODE = 'HR')")
    return gdf.to_crs(4326)


def ingest_municipalities(session: Session, settings: OtpornoSettings) -> int:
    """Download the LAU file (once) and load the Croatian municipalities."""
    dest = settings.raw_dir / "gisco" / settings.gisco_lau_url.rsplit("/", 1)[-1]
    dest.parent.mkdir(parents=True, exist_ok=True)
    with record_ingestion(session, SRC_LAU, settings.gisco_lau_url) as run:
        with http_mod.make_client(settings) as client:
            if not dest.exists():
                log.info("downloading_lau", url=settings.gisco_lau_url)
                _, sha = http_mod.download_file(client, settings.gisco_lau_url, dest)
                run.sha256 = sha
        gdf = read_croatia(dest)
        id_col = "LAU_ID" if "LAU_ID" in gdf.columns else "GISCO_ID"
        name_col = "LAU_NAME" if "LAU_NAME" in gdf.columns else "NAME_LATN"
        metric = gdf.to_crs(3765)
        rows = []
        for (_, row), area in zip(gdf.iterrows(), metric.geometry.area, strict=True):
            attrs = {
                k: (None if str(v) == "nan" else v)
                for k, v in row.items()
                if k not in ("geometry", id_col, name_col)
            }
            rows.append(
                {
                    "lau_id": str(row[id_col]),
                    "name": str(row[name_col]),
                    "wkt": as_multipolygon(row.geometry).wkt,
                    "area": round(area / 1e6, 3),
                    "attrs": json.dumps(attrs, default=str),
                }
            )
        session.execute(
            text(
                "insert into municipality (lau_id, name, geom, area_km2, attrs) "
                "values (:lau_id, :name, ST_Multi(ST_GeomFromText(:wkt, 4326)), :area, cast(:attrs as jsonb)) "
                "on conflict (lau_id) do update set name = excluded.name, geom = excluded.geom, "
                "area_km2 = excluded.area_km2, attrs = excluded.attrs"
            ),
            rows,
        )
        run.rows = len(rows)
    log.info("municipalities_loaded", rows=len(rows))
    return len(rows)
