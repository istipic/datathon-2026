"""Population grid -> ``cell`` (all of Croatia, with municipality)."""

from __future__ import annotations

import hashlib
from email.utils import parsedate_to_datetime
from pathlib import Path

import structlog
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from opendata_core import http as http_mod
from opendata_core import popgrid
from otporno_api.db import Cell
from otporno_api.settings import OtpornoSettings

log = structlog.get_logger(__name__)


def sha256_file(path: Path) -> str:
    """sha256 of a (large) file."""
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ensure_popgrid(session: Session, settings: OtpornoSettings) -> popgrid.PopGridLoad:
    """Download the Eurostat package if needed and load Croatia into ``popgrid_cell``."""
    settings.raw_dir.mkdir(parents=True, exist_ok=True)
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
    result = popgrid.load_popgrid(
        session, zip_path, sha256=sha256_file(zip_path), source_last_modified=modified
    )
    log.info("popgrid_loaded", rows=result.rows, has_age_groups=result.has_age_groups)
    return result


def build_cells(session: Session) -> int:
    """Fill ``cell`` from ``popgrid_cell``: WGS84 polygon, centroid, counts and the municipality that
    contains the centroid (a cell belongs to exactly one municipality)."""
    session.execute(
        text(
            """
            insert into cell (grd_id, geom, centroid, pop_total, pop_65p, lau_id)
            select p.grd_id,
                   ST_Transform(p.geom, 4326),
                   p.centroid,
                   p.pop_total::int,
                   p.pop_65plus,
                   (select m.lau_id from municipality m where ST_Intersects(m.geom, p.centroid) limit 1)
            from popgrid_cell p
            on conflict (grd_id) do update set
                geom = excluded.geom, centroid = excluded.centroid, pop_total = excluded.pop_total,
                pop_65p = excluded.pop_65p, lau_id = excluded.lau_id
            """
        )
    )
    session.commit()
    return int(session.scalar(select(func.count()).select_from(Cell)) or 0)


def ingest_grid(session: Session, settings: OtpornoSettings) -> dict[str, int | bool]:
    """``otporno ingest grid``: Eurostat grid -> ``popgrid_cell`` -> ``cell``."""
    loaded = ensure_popgrid(session, settings)
    n = build_cells(session)
    in_lau = int(
        session.scalar(select(func.count()).select_from(Cell).where(Cell.lau_id.is_not(None))) or 0
    )
    log.info("cells_built", cells=n, with_municipality=in_lau)
    return {"cells": n, "with_municipality": in_lau, "has_age_groups": loaded.has_age_groups}
