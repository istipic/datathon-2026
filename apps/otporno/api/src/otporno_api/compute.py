"""On-demand computation for a municipality that is not precomputed.

Steps: (1) public-building candidates from OSM, (2) the full Open-Meteo points of the municipality's most
populated 0.1 degree squares, as far as the free-tier quota allows without long waits, (3) ``heat_cell``
from the stored points (cells without their own point use the nearest one within 25 km), (4) status row.
Everything is cached in the database, so a second request is instant.
"""

from __future__ import annotations

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from otporno_api.constants import MODELS
from otporno_api.exposure import compute_municipality, set_status
from otporno_api.heat import fetch_full_point, stored_models
from otporno_api.om_client import OpenMeteoClient, QuotaExceeded
from otporno_api.settings import OtpornoSettings

log = structlog.get_logger(__name__)

MAX_POINTS = 6  # full points fetched on request (each costs ~780 of the 10 000 daily units)


def populated_points(
    session: Session, lau_id: str, limit: int = MAX_POINTS
) -> list[tuple[float, float]]:
    """0.1 degree squares of the municipality, most residents first."""
    rows = session.execute(
        text(
            """
            select round(ST_Y(centroid)::numeric, 1)::float lat, round(ST_X(centroid)::numeric, 1)::float lon,
                   sum(coalesce(pop_total, 0)) pop
            from cell where lau_id = :lau and coalesce(pop_total, 0) > 0
            group by 1, 2 order by pop desc limit :lim
            """
        ),
        {"lau": lau_id, "lim": limit},
    ).all()
    return [(r.lat, r.lon) for r in rows]


def run_compute(factory: sessionmaker[Session], settings: OtpornoSettings, lau_id: str) -> None:
    """Background job body; never raises (a failure is recorded in the status row)."""
    from otporno_api.ingest.buildings import ingest_buildings

    with factory() as session:
        try:
            set_status(session, lau_id, "computing", "Izračun je u tijeku.")
            try:
                sites = ingest_buildings(session, settings, lau_id)
            except (
                Exception
            ) as exc:  # candidates are optional: heat exposure still works without them
                log.warning("buildings_failed", lau=lau_id, error=str(exc)[:200])
                sites = {"error": type(exc).__name__}
            fetched, quota_stop = 0, False
            client = OpenMeteoClient(settings, factory, interactive=True)
            try:
                for lat, lon in populated_points(session, lau_id):
                    if len(stored_models(session, lat, lon, full=True)) >= len(MODELS):
                        continue
                    try:
                        fetch_full_point(client, session, lat, lon, batch=False, combined=True)
                        fetched += 1
                    except QuotaExceeded as exc:
                        quota_stop = True
                        log.warning("compute_quota", lau=lau_id, scope=exc.scope)
                        break
            finally:
                client.close()
            result = compute_municipality(session, lau_id)
            result["details"].update(
                {"buildings": sites, "points_fetched": fetched, "quota_stop": quota_stop}
            )
            if result["status"] == "ready":
                set_status(session, lau_id, "ready", None, result["details"])
        except Exception as exc:
            log.error("compute_failed", lau=lau_id, error=str(exc)[:300])
            session.rollback()
            set_status(
                session,
                lau_id,
                "failed",
                "Izračun nije uspio; pokušajte ponovno.",
                {"error": type(exc).__name__},
            )
