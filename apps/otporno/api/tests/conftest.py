"""Shared fixtures: REAL recorded data (Open-Meteo response, HV WMS capabilities, Karlovac cells/sites)."""

from __future__ import annotations

import csv
import json
import os
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

FIXTURES = Path(__file__).parent / "fixtures"
DB_FIXTURES = FIXTURES / "db"
API_DIR = Path(__file__).parents[1]
KARLOVAC = "HR_01791"


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    skip_live = pytest.mark.skip(reason="live network test: set RUN_LIVE=1")
    skip_db = pytest.mark.skip(
        reason="needs PostGIS: set TEST_DATABASE_URL (database name must end in _test)"
    )
    for item in items:
        if "live" in item.keywords and os.environ.get("RUN_LIVE") != "1":
            item.add_marker(skip_live)
        if "db" in item.keywords and not os.environ.get("TEST_DATABASE_URL"):
            item.add_marker(skip_db)


@pytest.fixture(scope="session")
def om_response() -> dict[str, Any]:
    """Real Climate API response for 45.5 N 15.5 E, 1991-2050, 3 models x (Tmax, Tmin), recorded 2026-11-04."""
    return json.loads(
        (FIXTURES / "2026-11-04_open_meteo_climate_45.5_15.5.json").read_text(encoding="utf-8")
    )


@pytest.fixture(scope="session")
def wms_capabilities() -> str:
    """Real GetCapabilities of https://servisi.voda.hr/wms recorded 2026-11-04."""
    return (FIXTURES / "2026-11-04_hv_wms_GetCapabilities.xml").read_text(encoding="utf-8")


def _rows(name: str) -> list[dict[str, str]]:
    with (DB_FIXTURES / name).open(encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


@pytest.fixture(scope="session")
def engine() -> Iterator[Engine]:
    """A PostGIS test database rebuilt with the Alembic migrations and seeded with real Karlovac data."""
    url = os.environ["TEST_DATABASE_URL"]
    assert url.rsplit("/", 1)[-1].endswith("_test"), (
        "refusing to wipe a database whose name does not end in _test"
    )
    eng = create_engine(url)
    with eng.begin() as conn:
        conn.execute(text("drop schema public cascade"))
        conn.execute(text("create schema public"))
        conn.execute(text("create extension if not exists postgis"))
    os.environ["DATABASE_URL"] = url
    from alembic import command
    from alembic.config import Config

    cfg = Config(str(API_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(API_DIR / "migrations"))
    command.upgrade(cfg, "head")
    yield eng
    eng.dispose()


class RecordedClient:
    """Stands in for ``OpenMeteoClient``: answers every request with the recorded real response."""

    def __init__(self, data: dict[str, Any]) -> None:
        self.data = data
        self.calls = 0

    def fetch(self, *args: Any, **kwargs: Any) -> Any:
        from otporno_api.om_client import Fetched

        self.calls += 1
        return Fetched(self.data, 939.2, 0.0)

    def close(self) -> None:
        pass


@pytest.fixture(scope="session")
def seeded(engine: Engine, om_response: dict[str, Any]) -> sessionmaker[Session]:
    """Karlovac municipality, cells, public buildings, 24 grid points, one address point, heat cells."""
    from otporno_api.actions import sync_rules
    from otporno_api.exposure import compute_municipality
    from otporno_api.heat import fetch_full_point
    from otporno_api.ingest.sources import register_all
    from otporno_api.settings import OtpornoSettings

    factory = sessionmaker(engine, expire_on_commit=False)
    settings = OtpornoSettings(
        _env_file=None,
        database_url=os.environ["TEST_DATABASE_URL"],
        contact_email="test@example.org",
    )
    with factory() as s:
        register_all(s, settings)
        m = _rows("2026-11-04_karlovac_municipality.csv")[0]
        s.execute(
            text(
                "insert into municipality (lau_id, name, area_km2, geom, attrs) values (:i, :n, :a, ST_GeomFromText(:w, 4326), '{}')"
            ),
            {"i": m["lau_id"], "n": m["name"], "a": float(m["area_km2"]), "w": m["wkt"]},
        )
        for c in _rows("2026-11-04_karlovac_cells.csv"):
            s.execute(
                text(
                    "insert into cell (grd_id, geom, centroid, pop_total, pop_65p, lau_id) values "
                    "(:g, ST_GeomFromText(:w, 4326), ST_GeomFromText(:c, 4326), :pt, :p65, :l)"
                ),
                {
                    "g": c["grd_id"],
                    "w": c["wkt"],
                    "c": c["centroid_wkt"],
                    "pt": int(c["pop_total"]) if c["pop_total"] else None,
                    "p65": int(c["pop_65p"]) if c["pop_65p"] else None,
                    "l": c["lau_id"],
                },
            )
        for site in _rows("2026-11-04_karlovac_sites.csv"):
            s.execute(
                text(
                    "insert into candidate_site (lau_id, name, kind, geom, source_id, osm_id) values "
                    "(:l, :n, :k, ST_GeomFromText(:w, 4326), 'osm-public-buildings', :o)"
                ),
                {
                    "l": KARLOVAC,
                    "n": site["name"] or None,
                    "k": site["kind"],
                    "w": site["wkt"],
                    "o": site["osm_id"],
                },
            )
        for p in _rows("2026-11-04_open_meteo_grid_points.csv"):
            s.execute(
                text(
                    "insert into heat_point (lat_r, lon_r, model, fut_hot_days, kind) values (:a, :o, :m, :f, 'grid')"
                ),
                {"a": p["lat_r"], "o": p["lon_r"], "m": p["model"], "f": float(p["fut_hot_days"])},
            )
        s.commit()
        sync_rules(s)
        fetch_full_point(RecordedClient(om_response), s, 45.5, 15.5, batch=True, combined=True)  # type: ignore[arg-type]
        compute_municipality(s, KARLOVAC)
    return factory
