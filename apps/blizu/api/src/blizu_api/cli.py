"""``blizu`` command line: ingestion steps and validation."""

from __future__ import annotations

import time
from collections.abc import Callable

import structlog
import typer
from sqlalchemy.orm import Session

from blizu_api.db import make_session_factory
from blizu_api.settings import BlizuSettings, get_settings
from opendata_core.logging import configure_logging

app = typer.Typer(help="Blizu: ingestion and validation", no_args_is_help=True)
ingest_app = typer.Typer(help="Load data sources and derive artefacts", no_args_is_help=True)
app.add_typer(ingest_app, name="ingest")

log = structlog.get_logger("blizu.cli")

Step = Callable[[Session, BlizuSettings], object]


def _run(name: str, step: Step) -> None:
    settings = get_settings()
    configure_logging(settings)
    if not settings.database_url:
        raise typer.BadParameter("DATABASE_URL is not set (see apps/blizu/.env.example)")
    if not settings.contact_email:
        raise typer.BadParameter(
            "CONTACT_EMAIL is not set: external sources need an identifying User-Agent"
        )
    t0 = time.time()
    with make_session_factory(settings)() as session:
        step(session, settings)
    log.info("step_done", step=name, seconds=round(time.time() - t0, 1))


def step_sources(session: Session, settings: BlizuSettings) -> None:
    """Register all data sources (reads CKAN metadata)."""
    from blizu_api.ingest.sources import register_ckan_sources, register_static_sources
    from opendata_core import http as http_mod
    from opendata_core.ckan import CkanClient
    from opendata_core.popgrid import register_popgrid_source

    with http_mod.make_client(settings) as client:
        register_ckan_sources(session, CkanClient(settings, client=client))
    register_static_sources(session)
    register_popgrid_source(session)
    session.commit()


def step_graph(session: Session, settings: BlizuSettings) -> None:
    """Download the OSM walking network and build both graphs."""
    from blizu_api.ingest.graph import ingest_graph

    ingest_graph(session, settings)


def step_facilities(session: Session, settings: BlizuSettings) -> None:
    """Load facilities (official + OSM), dedupe."""
    from blizu_api.ingest.facilities import ingest_facilities

    ingest_facilities(session, settings)


def step_gtfs(session: Session, settings: BlizuSettings) -> None:
    """Download ZET GTFS and compute stop frequencies."""
    from blizu_api.ingest.gtfs import ingest_gtfs

    ingest_gtfs(session, settings)


def step_access(session: Session, settings: BlizuSettings) -> None:
    """Network distances from every node to the nearest facility."""
    from blizu_api.ingest.access import ingest_access

    ingest_access(session, settings)


def step_grid(session: Session, settings: BlizuSettings) -> None:
    """Population grid clipped to Zagreb and per-cell access."""
    from blizu_api.ingest.grid import ingest_grid

    ingest_grid(session, settings)


STEPS: dict[str, Step] = {
    "sources": step_sources,
    "graph": step_graph,
    "facilities": step_facilities,
    "gtfs": step_gtfs,
    "access": step_access,
    "grid": step_grid,
}
ORDER = ["sources", "graph", "facilities", "gtfs", "access", "grid"]


@ingest_app.command("sources")
def ingest_sources() -> None:
    """Register data sources."""
    _run("sources", step_sources)


@ingest_app.command("graph")
def ingest_graph_cmd() -> None:
    """Build the walking graphs from OpenStreetMap."""
    _run("graph", step_graph)


@ingest_app.command("facilities")
def ingest_facilities_cmd() -> None:
    """Load facilities into the database."""
    _run("facilities", step_facilities)


@ingest_app.command("gtfs")
def ingest_gtfs_cmd() -> None:
    """ZET GTFS: stop frequencies (public transport)."""
    _run("gtfs", step_gtfs)


@ingest_app.command("access")
def ingest_access_cmd() -> None:
    """Compute network distances to the nearest facility."""
    _run("access", step_access)


@ingest_app.command("grid")
def ingest_grid_cmd() -> None:
    """Population grid and per-cell access."""
    _run("grid", step_grid)


@ingest_app.command("all")
def ingest_all() -> None:
    """Run every step in dependency order."""
    for name in ORDER:
        _run(name, STEPS[name])


@app.command("validate")
def validate(
    samples: int = typer.Option(20, help="Number of random origin/category pairs"),
) -> None:
    """Compare our walking distances with OSRM (foot profile) and write docs/validation.md."""
    from blizu_api.validate import run_validation

    settings = get_settings()
    configure_logging(settings)
    run_validation(settings, samples)


if __name__ == "__main__":
    app()
