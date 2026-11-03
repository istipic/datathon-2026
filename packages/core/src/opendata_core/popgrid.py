"""Eurostat Census 2021 1 km population grid, restricted to Croatia.

Source (verified 2026-11-03, see ``packages/core/data/evidence/``): the official EU-wide package
``Eurostat_Census-GRID_2021_V3.zip`` from Eurostat GISCO. Its CSV has the fields
``GRD_ID, T, M, F, Y_LT15, Y_1564, Y_GE65, ..., LAND_SURFACE, POPULATED, CNTR_ID``; ``-8888``
(confidentiality) and ``-9999`` (other) mean "not available". ``GRD_ID`` is
``CRS3035RES<res>mN<northing>E<easting>`` — the *south-west* corner of the cell in EPSG:3035
(checked against the official GPKG polygons). A cell belongs to Croatia when ``CNTR_ID`` (a
dash-separated list of reporting countries) contains ``HR``; the 1 064 shared border cells also
contain neighbouring countries' residents, so totals slightly exceed the national census count.
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import IO, Any, NamedTuple

import httpx
import numpy as np
import pandas as pd
from geoalchemy2 import Geometry
from pyproj import Transformer
from sqlalchemy import BigInteger, Boolean, Float, Integer, String, delete, func, insert, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from opendata_core import http as http_mod
from opendata_core.db import Base
from opendata_core.provenance import AccessMethod, Tier, record_ingestion, register_source

SOURCE_ID = "eurostat-census-grid-2021"
LANDING_URL = (
    "https://ec.europa.eu/eurostat/web/gisco/geodata/population-distribution/population-grids"
)
DOWNLOAD_URL = "https://gisco-services.ec.europa.eu/census/2021/Eurostat_Census-GRID_2021_V3.zip"
CSV_SUFFIX = "ESTAT_Census_2021_V3.csv"
COPYRIGHT_URL = "https://ec.europa.eu/eurostat/web/main/about-us/policies/copyright"
SRC_CRS = 3035
_GRD_RE = re.compile(r"^CRS3035RES(\d+)mN(\d+)E(\d+)$")
_HR_RE = r"(?:^|-)HR(?:-|$)"
_USECOLS = ["GRD_ID", "T", "Y_LT15", "Y_1564", "Y_GE65", "LAND_SURFACE", "POPULATED", "CNTR_ID"]
_COUNT_COLS = {
    "T": "pop_total",
    "Y_LT15": "pop_under15",
    "Y_1564": "pop_15_64",
    "Y_GE65": "pop_65plus",
}
_BATCH = 5000


class PopGridCell(Base):
    """One 1 km census grid cell (geometry in EPSG:3035, centroid in WGS84)."""

    __tablename__ = "popgrid_cell"

    grd_id: Mapped[str] = mapped_column(String(48), primary_key=True)
    geom: Mapped[Any] = mapped_column(Geometry("POLYGON", srid=SRC_CRS, spatial_index=True))
    centroid: Mapped[Any] = mapped_column(Geometry("POINT", srid=4326, spatial_index=True))
    pop_total: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    pop_under15: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pop_15_64: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pop_65plus: Mapped[int | None] = mapped_column(Integer, nullable=True)
    land_surface: Mapped[float | None] = mapped_column(Float, nullable=True)
    populated: Mapped[bool] = mapped_column(Boolean)
    cntr_id: Mapped[str] = mapped_column(String(32))


class GridCellId(NamedTuple):
    """Parsed ``GRD_ID``."""

    res_m: int
    northing: int
    easting: int


def parse_grd_id(grd_id: str) -> GridCellId:
    """Parse ``CRS3035RES1000mN2490000E4595000`` into resolution, northing, easting."""
    m = _GRD_RE.match(grd_id)
    if not m:
        raise ValueError(f"unrecognised GRD_ID: {grd_id!r}")
    return GridCellId(int(m[1]), int(m[2]), int(m[3]))


def cell_bounds_3035(grd_id: str) -> tuple[float, float, float, float]:
    """``(minx, miny, maxx, maxy)`` of the cell in EPSG:3035 (GRD_ID is the SW corner)."""
    cid = parse_grd_id(grd_id)
    return (cid.easting, cid.northing, cid.easting + cid.res_m, cid.northing + cid.res_m)


def clean_count(series: pd.Series) -> pd.Series:
    """Map the not-available codes (any negative value, i.e. -8888/-9999) to ``<NA>``."""
    numeric = pd.to_numeric(series, errors="coerce").astype("Int64")
    return numeric.mask(numeric < 0)


def _open_csv(path: Path) -> tuple[IO[bytes], zipfile.ZipFile | None]:
    if path.suffix.lower() == ".zip":
        zf = zipfile.ZipFile(path)
        members = [n for n in zf.namelist() if n.endswith(CSV_SUFFIX)]
        if not members:
            zf.close()
            raise ValueError(f"{path.name}: no member ending in {CSV_SUFFIX}")
        return zf.open(members[0]), zf
    return path.open("rb"), None


def read_croatia_cells(path: Path) -> pd.DataFrame:
    """Read Croatian cells from the Eurostat package (``.zip``) or its CSV.

    Returns a DataFrame with ``grd_id, pop_total, pop_under15, pop_15_64, pop_65plus (Int64,
    <NA> when unavailable), land_surface, populated (bool), cntr_id``. Streams in chunks, so the
    340 MB CSV is never fully in memory.
    """
    fh, zf = _open_csv(path)
    try:
        parts = []
        for chunk in pd.read_csv(
            fh, usecols=_USECOLS, dtype={"GRD_ID": str, "CNTR_ID": str}, chunksize=500_000
        ):
            mask = chunk["CNTR_ID"].fillna("").str.contains(_HR_RE, regex=True)
            if mask.any():
                parts.append(chunk[mask])
    finally:
        fh.close()
        if zf is not None:
            zf.close()
    if not parts:
        raise ValueError("no Croatian (CNTR_ID contains HR) cells found; wrong file?")
    raw = pd.concat(parts, ignore_index=True)
    out = pd.DataFrame({"grd_id": raw["GRD_ID"]})
    for src, dst in _COUNT_COLS.items():
        out[dst] = clean_count(raw[src])
    out["land_surface"] = pd.to_numeric(raw["LAND_SURFACE"], errors="coerce")
    out["populated"] = raw["POPULATED"].astype(int).astype(bool)
    out["cntr_id"] = raw["CNTR_ID"]
    return out


def has_age_groups(cells: pd.DataFrame) -> bool:
    """True if age-group counts exist (at least one non-null ``pop_65plus`` value)."""
    return bool(cells["pop_65plus"].notna().any())


def _polygon_wkt(minx: float, miny: float, maxx: float, maxy: float) -> str:
    return (
        f"POLYGON(({minx:.0f} {miny:.0f},{maxx:.0f} {miny:.0f},{maxx:.0f} {maxy:.0f},"
        f"{minx:.0f} {maxy:.0f},{minx:.0f} {miny:.0f}))"
    )


def _na(value: Any) -> Any:
    return None if pd.isna(value) else value


@dataclass(frozen=True)
class PopGridLoad:
    """Result of :func:`load_popgrid`."""

    rows: int
    has_age_groups: bool


def download_popgrid(client: httpx.Client, dest_dir: Path) -> tuple[Path, str]:
    """Download the official package; returns ``(path, sha256)``. ~540 MB — do it once."""
    return http_mod.download_file(
        client, DOWNLOAD_URL, dest_dir / "Eurostat_Census-GRID_2021_V3.zip"
    )


def register_popgrid_source(session: Session) -> None:
    """Register the ``eurostat-census-grid-2021`` data source."""
    register_source(
        session,
        id=SOURCE_ID,
        title="Census 2021 population grid, 1 km² (version 3)",
        publisher="Eurostat (GISCO)",
        url=LANDING_URL,
        license_name="Eurostat copyright policy (source must be indicated; modifications stated)",
        license_url=COPYRIGHT_URL,
        access_method=AccessMethod.download,
        tier=Tier.eu_official,
        notes=(
            "Cells with CNTR_ID containing HR. Border cells shared with SI/HU also contain "
            "neighbouring residents. -8888/-9999 loaded as NULL. Derived from GRD_ID: polygon "
            "(EPSG:3035, SW corner + 1 km) and WGS84 centroid."
        ),
    )


def load_popgrid(
    session: Session,
    path: Path,
    *,
    sha256: str | None = None,
    source_last_modified: datetime | None = None,
    url: str = DOWNLOAD_URL,
) -> PopGridLoad:
    """Replace ``popgrid_cell`` with the Croatian cells from ``path`` (zip or csv).

    Registers the data source and records an ``ingestion_run``. Needs PostgreSQL + PostGIS.
    """
    register_popgrid_source(session)
    session.commit()
    with record_ingestion(session, SOURCE_ID, url) as run:
        cells = read_croatia_cells(path)
        ages = has_age_groups(cells)
        bounds = np.array([cell_bounds_3035(g) for g in cells["grd_id"]], dtype=float)
        tr = Transformer.from_crs(SRC_CRS, 4326, always_xy=True)
        lon, lat = tr.transform(
            (bounds[:, 0] + bounds[:, 2]) / 2, (bounds[:, 1] + bounds[:, 3]) / 2
        )
        session.execute(delete(PopGridCell))
        records = []
        for i, row in enumerate(cells.itertuples(index=False)):
            b = bounds[i]
            records.append(
                {
                    "grd_id": row.grd_id,
                    "geom": f"SRID={SRC_CRS};{_polygon_wkt(*b)}",
                    "centroid": f"SRID=4326;POINT({lon[i]:.6f} {lat[i]:.6f})",
                    "pop_total": _na(row.pop_total),
                    "pop_under15": _na(row.pop_under15),
                    "pop_15_64": _na(row.pop_15_64),
                    "pop_65plus": _na(row.pop_65plus),
                    "land_surface": _na(row.land_surface),
                    "populated": bool(row.populated),
                    "cntr_id": row.cntr_id,
                }
            )
            if len(records) >= _BATCH:
                session.execute(insert(PopGridCell), records)
                records = []
        if records:
            session.execute(insert(PopGridCell), records)
        run.rows = len(cells)
        run.sha256 = sha256
        run.source_last_modified = source_last_modified
    return PopGridLoad(rows=len(cells), has_age_groups=ages)


def popgrid_has_age_groups(session: Session) -> bool:
    """Apps call this to decide whether age-based weighting is possible (else fall back)."""
    count = session.scalar(select(func.count()).where(PopGridCell.pop_65plus.is_not(None)))
    return bool(count)
