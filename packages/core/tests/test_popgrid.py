"""popgrid tests on REAL rows excerpted from Eurostat Census-GRID V3 (retrieved 2026-11-03)."""

from __future__ import annotations

import os
import zipfile
from pathlib import Path

import httpx
import pandas as pd
import pytest
import respx
import sqlalchemy as sa
from sqlalchemy.orm import Session

from opendata_core import popgrid
from opendata_core.config import CoreSettings

FIXTURE = "eurostat/2026-11-03_census_grid_v3_sample.csv"


@pytest.fixture
def csv_path(fixtures_dir: Path) -> Path:
    return fixtures_dir / FIXTURE


@pytest.fixture
def zip_path(csv_path: Path, tmp_path: Path) -> Path:
    """Package the real excerpt with the member name used by the official V3 zip."""
    out = tmp_path / "Eurostat_Census-GRID_2021_V3.zip"
    with zipfile.ZipFile(out, "w") as zf:
        zf.write(csv_path, "Eurostat_Census-GRID_2021_V3/ESTAT_Census_2021_V3.csv")
    return out


def test_parse_grd_id() -> None:
    cid = popgrid.parse_grd_id("CRS3035RES1000mN2490000E4595000")
    assert (cid.res_m, cid.northing, cid.easting) == (1000, 2490000, 4595000)
    for bad in ["", "CRS3035RES1000m", "CRS3035RES1000mN1E2x", "HR_unallocated"]:
        with pytest.raises(ValueError, match="GRD_ID"):
            popgrid.parse_grd_id(bad)


def test_cell_bounds_match_official_gpkg_polygon() -> None:
    # Verified against the official GPKG polygon of this cell (see data/evidence).
    assert popgrid.cell_bounds_3035("CRS3035RES1000mN2490000E4595000") == (
        4595000,
        2490000,
        4596000,
        2491000,
    )


def test_read_croatia_cells_filters_and_cleans(csv_path: Path) -> None:
    cells = popgrid.read_croatia_cells(csv_path)
    assert len(cells) == 10  # 1 AT-CH row excluded; HR, HR-SI and HR-HU rows kept
    assert not cells["grd_id"].str.contains("N2684000E4286000").any()
    assert set(cells["cntr_id"]) == {"HR", "HR-SI", "HR-HU"}
    row = cells[cells["grd_id"] == "CRS3035RES1000mN2463000E4603000"].iloc[0]
    assert (row.pop_total, row.pop_under15, row.pop_15_64, row.pop_65plus) == (722, 78, 426, 219)
    assert row.populated
    assert row.land_surface == pytest.approx(0.3867)
    empty = cells[cells["grd_id"] == "CRS3035RES1000mN2458000E4602000"].iloc[0]
    assert empty.pop_total == 0
    assert not empty.populated
    assert str(cells["pop_total"].dtype) == "Int64"


def test_read_from_official_zip_member_name(zip_path: Path, csv_path: Path) -> None:
    from_zip = popgrid.read_croatia_cells(zip_path)
    from_csv = popgrid.read_croatia_cells(csv_path)
    pd.testing.assert_frame_equal(from_zip, from_csv)


def test_zip_without_expected_member(tmp_path: Path, csv_path: Path) -> None:
    bad = tmp_path / "bad.zip"
    with zipfile.ZipFile(bad, "w") as zf:
        zf.write(csv_path, "other.csv")
    with pytest.raises(ValueError, match="no member"):
        popgrid.read_croatia_cells(bad)


def test_file_without_croatian_cells(tmp_path: Path, csv_path: Path) -> None:
    lines = csv_path.read_text().splitlines()
    only_at = tmp_path / "at.csv"
    only_at.write_text("\n".join([lines[0], lines[1]]) + "\n")  # header + the real AT-CH row
    with pytest.raises(ValueError, match="no Croatian"):
        popgrid.read_croatia_cells(only_at)


def test_clean_count_maps_not_available_codes_to_na() -> None:
    # -8888 = confidentiality, -9999 = other reasons (Eurostat read.me).
    out = popgrid.clean_count(pd.Series([5, -8888, -9999, 0, None]))
    assert out.isna().tolist() == [False, True, True, False, True]
    assert out.dropna().tolist() == [5, 0]


def test_has_age_groups(csv_path: Path) -> None:
    cells = popgrid.read_croatia_cells(csv_path)
    assert popgrid.has_age_groups(cells) is True
    stripped = cells.assign(pop_65plus=pd.array([pd.NA] * len(cells), dtype="Int64"))
    assert popgrid.has_age_groups(stripped) is False


def test_polygon_wkt_is_closed_ring() -> None:
    wkt = popgrid._polygon_wkt(4595000, 2490000, 4596000, 2491000)
    assert wkt == (
        "POLYGON((4595000 2490000,4596000 2490000,4596000 2491000,4595000 2491000,4595000 2490000))"
    )


@respx.mock
def test_download_popgrid_uses_official_url(tmp_path: Path, settings: CoreSettings) -> None:
    route = respx.get(popgrid.DOWNLOAD_URL).respond(200, content=b"zipbytes")
    from opendata_core import http as h

    with h.make_client(settings) as client:
        path, sha = popgrid.download_popgrid(client, tmp_path)
    assert route.called
    assert path.name == "Eurostat_Census-GRID_2021_V3.zip"
    assert len(sha) == 64


@pytest.mark.db
def test_load_popgrid_into_postgis(zip_path: Path) -> None:
    """Integration test against real PostGIS (set TEST_DATABASE_URL)."""
    from opendata_core.db import Base
    from opendata_core.provenance import IngestionRun, sources_summary

    engine = sa.create_engine(os.environ["TEST_DATABASE_URL"])
    with engine.begin() as conn:
        conn.execute(sa.text("CREATE EXTENSION IF NOT EXISTS postgis"))
        Base.metadata.drop_all(conn)
        Base.metadata.create_all(conn)
    try:
        with Session(engine) as session:
            result = popgrid.load_popgrid(session, zip_path, sha256="ab" * 32)
            assert result.rows == 10
            assert result.has_age_groups is True
            assert popgrid.popgrid_has_age_groups(session) is True
            n = session.scalar(sa.text("select count(*) from popgrid_cell"))
            assert n == 10
            lon, lat, area = session.execute(
                sa.text(
                    "select st_x(centroid), st_y(centroid), st_area(geom) from popgrid_cell "
                    "where grd_id = 'CRS3035RES1000mN2463000E4603000'"
                )
            ).one()
            assert 13.0 < lon < 19.5
            assert 42.2 < lat < 46.6
            assert area == pytest.approx(1_000_000)
            run = session.query(IngestionRun).one()
            assert run.rows == 10
            assert run.status.value == "ok"
            [src] = sources_summary(session)
            assert src["id"] == popgrid.SOURCE_ID
            assert src["tier"] == "eu_official"
            # reloading replaces, not duplicates
            popgrid.load_popgrid(session, zip_path)
            assert session.scalar(sa.text("select count(*) from popgrid_cell")) == 10
    finally:
        with engine.begin() as conn:
            Base.metadata.drop_all(conn)
        engine.dispose()
    assert httpx  # keep the import used for type parity with other test modules
