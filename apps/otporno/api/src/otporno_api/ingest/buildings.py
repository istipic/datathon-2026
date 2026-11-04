"""Cooling-centre candidates: public OSM buildings per municipality.

amenity in (library, school, community_centre, social_facility, townhall). Overpass is tried first (two
attempts); when it is down the Geofabrik Croatia extract is read with ``osmium`` (same fallback pattern
as docs/adr/0005-geofabrik-fallback-for-osm-features.md, recorded for this app in docs/adr/0007).
"""

from __future__ import annotations

from pathlib import Path
from typing import Any, cast

import httpx
import structlog
from sqlalchemy import delete, text
from sqlalchemy.orm import Session

from opendata_core import http as http_mod
from opendata_core.provenance import record_ingestion
from otporno_api.constants import SRC_OSM_BUILDINGS
from otporno_api.db import CandidateSite
from otporno_api.settings import OtpornoSettings

log = structlog.get_logger(__name__)

KINDS = ("library", "school", "community_centre", "social_facility", "townhall")
PBF_URL = "https://download.geofabrik.de/europe/croatia-latest.osm.pbf"
DEDUPE_DEG = 0.0004  # ~35 m: a school is often mapped as a node and as a building


def overpass_query(bbox: tuple[float, float, float, float]) -> str:
    """Overpass QL for the public amenities inside ``(min_lon, min_lat, max_lon, max_lat)``."""
    w, s, e, n = bbox
    kinds = "|".join(KINDS)
    return f'[out:json][timeout:90];nwr["amenity"~"^({kinds})$"]({s},{w},{n},{e});out center tags;'


def parse_overpass(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Sites from an Overpass JSON response (nodes, and ways/relations via ``center``)."""
    out = []
    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        kind = tags.get("amenity")
        if kind not in KINDS:
            continue
        lon = el.get("lon") if el["type"] == "node" else (el.get("center") or {}).get("lon")
        lat = el.get("lat") if el["type"] == "node" else (el.get("center") or {}).get("lat")
        if lon is None or lat is None:
            continue
        out.append(
            {
                "osm_id": f"{el['type'][0]}{el['id']}",
                "name": tags.get("name"),
                "kind": kind,
                "lon": float(lon),
                "lat": float(lat),
            }
        )
    return out


def fetch_overpass(
    settings: OtpornoSettings, bbox: tuple[float, float, float, float]
) -> list[dict[str, Any]]:
    """Overpass with two attempts; raises on failure so the caller can fall back to the extract."""
    last: Exception | None = None
    with http_mod.make_client(settings) as client:
        for _ in range(2):
            try:
                response = client.post(
                    settings.overpass_url, data={"data": overpass_query(bbox)}, timeout=120
                )
                response.raise_for_status()
                return parse_overpass(response.json())
            except (httpx.HTTPError, ValueError) as exc:
                last = exc
                log.warning("overpass_failed", error=type(exc).__name__)
    raise RuntimeError(f"Overpass unavailable: {type(last).__name__}")


def ensure_pbf(settings: OtpornoSettings) -> Path:
    """The Geofabrik Croatia extract (downloaded once, ~200 MB)."""
    path = settings.raw_dir / "croatia-latest.osm.pbf"
    if not path.exists():
        settings.raw_dir.mkdir(parents=True, exist_ok=True)
        with http_mod.make_client(settings) as client:
            log.info("downloading_geofabrik_extract")
            http_mod.download_file(client, PBF_URL, path)
    return path


def read_pbf(pbf: Path, bbox: tuple[float, float, float, float]) -> list[dict[str, Any]]:
    """Sites from the extract (``osmium``; ways are placed at the mean of their node locations)."""
    import osmium  # imported lazily: only needed for the fallback

    w, s, e, n = bbox
    out: list[dict[str, Any]] = []
    fp = (
        osmium.FileProcessor(str(pbf))
        .with_locations()
        .with_filter(osmium.filter.KeyFilter("amenity"))
    )
    for obj in fp:  # osmium yields a union of element types: treat as Any
        obj = cast(Any, obj)
        kind = obj.tags.get("amenity")
        if kind not in KINDS:
            continue
        if obj.is_node():
            lon, lat = obj.lon, obj.lat
        elif obj.is_way():
            pts = [(nd.lon, nd.lat) for nd in obj.nodes if nd.location.valid()]
            if not pts:
                continue
            lon = sum(p[0] for p in pts) / len(pts)
            lat = sum(p[1] for p in pts) / len(pts)
        else:
            continue
        if w <= lon <= e and s <= lat <= n:
            out.append(
                {
                    "osm_id": f"{'n' if obj.is_node() else 'w'}{obj.id}",
                    "name": obj.tags.get("name"),
                    "kind": kind,
                    "lon": lon,
                    "lat": lat,
                }
            )
    return out


def dedupe(sites: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Merge duplicates: same kind and name within ~35 m (prefer the entry that has a name)."""
    seen: dict[tuple[str, str, int, int], dict[str, Any]] = {}
    for s in sorted(sites, key=lambda x: (x["name"] is None, x["osm_id"])):
        key = (
            s["kind"],
            (s["name"] or "").lower(),
            round(s["lon"] / DEDUPE_DEG),
            round(s["lat"] / DEDUPE_DEG),
        )
        seen.setdefault(key, s)
    return list(seen.values())


def ingest_buildings(session: Session, settings: OtpornoSettings, lau_id: str) -> dict[str, Any]:
    """Load the candidate sites of one municipality (replaces its previous candidates)."""
    row = session.execute(
        text(
            "select ST_XMin(geom) w, ST_YMin(geom) s, ST_XMax(geom) e, ST_YMax(geom) n from municipality where lau_id = :l"
        ),
        {"l": lau_id},
    ).one_or_none()
    if row is None:
        raise ValueError(f"unknown municipality {lau_id}")
    bbox = (float(row.w), float(row.s), float(row.e), float(row.n))
    with record_ingestion(
        session, SRC_OSM_BUILDINGS, f"{settings.overpass_url} (bbox of {lau_id})"
    ) as run:
        via = "overpass"
        try:
            sites = fetch_overpass(settings, bbox)
        except RuntimeError:
            via = "geofabrik-extract"
            sites = read_pbf(ensure_pbf(settings), bbox)
        sites = dedupe(sites)
        kept = [
            s
            for s in sites
            if session.scalar(
                text(
                    "select ST_Within(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), "
                    "(select geom from municipality where lau_id = :l))"
                ),
                {"lon": s["lon"], "lat": s["lat"], "l": lau_id},
            )
        ]
        session.execute(delete(CandidateSite).where(CandidateSite.lau_id == lau_id))
        for s in kept:
            session.execute(
                text(
                    "insert into candidate_site (lau_id, name, kind, geom, source_id, osm_id) "
                    "values (:l, :name, :kind, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :src, :osm)"
                ),
                {
                    "l": lau_id,
                    "name": s["name"],
                    "kind": s["kind"],
                    "lon": s["lon"],
                    "lat": s["lat"],
                    "src": SRC_OSM_BUILDINGS,
                    "osm": s["osm_id"],
                },
            )
        run.rows = len(kept)
    result = {
        "lau_id": lau_id,
        "via": via,
        "fetched": len(sites),
        "inside": len(kept),
        "by_kind": {k: sum(1 for s in kept if s["kind"] == k) for k in KINDS},
    }
    log.info("candidate_sites_loaded", **result)
    return result
