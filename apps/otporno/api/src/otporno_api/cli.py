"""``otporno`` command line: ingestion steps, validation and background jobs."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

import structlog
import typer
from sqlalchemy.orm import Session

from opendata_core.logging import configure_logging
from otporno_api.db import make_session_factory
from otporno_api.settings import OtpornoSettings, get_settings

app = typer.Typer(help="Otporko: ingestion and validation", no_args_is_help=True)
ingest_app = typer.Typer(help="Load data sources and derive artefacts", no_args_is_help=True)
app.add_typer(ingest_app, name="ingest")

log = structlog.get_logger("otporno.cli")

Step = Callable[[Session, OtpornoSettings], Any]


def _run(name: str, step: Step) -> Any:
    settings = get_settings()
    configure_logging(settings)
    if not settings.database_url:
        raise typer.BadParameter("DATABASE_URL is not set (see apps/otporno/.env.example)")
    if not settings.contact_email:
        raise typer.BadParameter(
            "CONTACT_EMAIL is not set: external sources need an identifying User-Agent"
        )
    t0 = time.time()
    with make_session_factory(settings)() as session:
        result = step(session, settings)
    log.info("step_done", step=name, seconds=round(time.time() - t0, 1))
    return result


def _echo(result: Any) -> None:
    typer.echo(json.dumps(result, indent=2, ensure_ascii=False, default=str))


@ingest_app.command("sources")
def sources() -> None:
    """Register all data sources."""
    from otporno_api.ingest.sources import register_all

    _run("sources", register_all)


@ingest_app.command("municipalities")
def municipalities() -> None:
    """Load Croatian municipalities (GISCO LAU 2024)."""
    from otporno_api.ingest.municipalities import ingest_municipalities

    _echo({"municipalities": _run("municipalities", ingest_municipalities)})


@ingest_app.command("grid")
def grid() -> None:
    """Eurostat Census 2021 grid -> cell (whole of Croatia, with municipality)."""
    from otporno_api.ingest.grid import ingest_grid

    _echo(_run("grid", ingest_grid))


@ingest_app.command("heat-grid")
def heat_grid(
    lau: list[str] = typer.Option(
        [],
        "--lau",
        help="Municipality ids whose 0.1 degree points are fetched after the first grid points",
    ),
    grid_first: int = typer.Option(30, help="Grid points fetched before the municipality points"),
    max_requests: int | None = typer.Option(None, help="Stop after this many fetched points"),
) -> None:
    """Fetch Open-Meteo climate data for the national 0.25 degree grid and municipality points.

    Quota-aware (free tier: ~10 full requests per day): sleeps until budget is free and resumes where it
    stopped. Run it detached; it can take days."""
    from otporno_api.heat import run_heat_job
    from otporno_api.om_client import OpenMeteoClient

    def step(session: Session, settings: OtpornoSettings) -> dict[str, int]:
        client = OpenMeteoClient(settings, make_session_factory(settings))
        try:
            return run_heat_job(
                client, session, lau_ids=lau, grid_first=grid_first, max_requests=max_requests
            )
        finally:
            client.close()

    _echo(_run("heat-grid", step))


@ingest_app.command("heat-cells")
def heat_cells(lau: str = typer.Option(..., "--lau", help="Municipality id")) -> None:
    """Build heat_cell for a municipality from the stored heat points and update its status."""
    from otporno_api.exposure import compute_municipality

    _echo(_run("heat-cells", lambda s, st: compute_municipality(s, lau)))


@ingest_app.command("buildings")
def buildings(lau: str = typer.Option(..., "--lau", help="Municipality id")) -> None:
    """Cooling-centre candidates (public OSM buildings) of a municipality."""
    from otporno_api.ingest.buildings import ingest_buildings

    _echo(_run("buildings", lambda s, st: ingest_buildings(s, st, lau)))


@ingest_app.command("actions")
def actions() -> None:
    """Load the cited action rules (config/action_rules.yaml) into action_rule."""
    from otporno_api.actions import sync_rules

    _echo({"action_rules": _run("actions", lambda s, st: sync_rules(s)).__int__()})


@ingest_app.command("flood")
def flood(lau: str = typer.Option(..., "--lau", help="Municipality id")) -> None:
    """Flood data for a municipality: walks the access ladder against the live Hrvatske vode WMS.

    Result today: ladder step c (hazard layers are not queryable, WFS disabled, no vector download), so
    nothing is stored per cell; the command records the check and the evidence summary."""
    from opendata_core.provenance import record_ingestion
    from otporno_api.constants import SRC_HV_FLOOD
    from otporno_api.flood_wms import (
        fetch_capabilities,
        hazard_layers,
        ladder_step,
        parse_capabilities,
    )

    def step(session: Session, settings: OtpornoSettings) -> dict[str, Any]:
        with record_ingestion(session, SRC_HV_FLOOD, settings.hv_wms_url) as run:
            layers = parse_capabilities(fetch_capabilities(settings))
            found = hazard_layers(layers)
            run.rows = sum(1 for v in found.values() if v is not None)
        return {
            "lau_id": lau,
            "ladder": ladder_step(layers),
            "layers": {
                k: (None if v is None else {"name": v.name, "queryable": v.queryable})
                for k, v in found.items()
            },
            "stored_flood_cells": 0,
            "note": "Ladder c: WMS overlay only; flood level is not derived (see docs/adr/0007).",
        }

    _echo(_run("flood", step))


@ingest_app.command("corine")
def corine() -> None:
    """CORINE Land Cover 2018 (fire exposure): checks the EEA map service and records the check.

    The service answers point queries, so nothing is stored per cell; the passport queries it on
    demand (cached 24 h in memory)."""
    import httpx

    from opendata_core import http as http_mod
    from opendata_core.provenance import record_ingestion
    from otporno_api.constants import SRC_CORINE
    from otporno_api.fire import VEGETATION, fetch

    def step(session: Session, settings: OtpornoSettings) -> dict[str, Any]:
        with record_ingestion(session, SRC_CORINE, settings.corine_url) as run:
            with http_mod.make_client(settings) as client:
                info = client.get(settings.corine_url, params={"f": "json"})
                info.raise_for_status()
                layers = [lyr["name"] for lyr in info.json().get("layers", [])[:3]]
                try:  # centre of Karlovac: an end-to-end probe of both identify queries
                    probe = fetch(settings, 15.5553, 45.4929, client)
                except httpx.HTTPError as exc:
                    raise RuntimeError(f"identify failed: {type(exc).__name__}") from exc
            run.rows = 1
        return {
            "layers": layers,
            "vegetation_classes": sorted(VEGETATION),
            "probe_karlovac": {"code": probe.code_at_point, "band": probe.band},
            "stored_cells": 0,
            "note": "Point-query service: nothing is downloaded; see otporno_api/fire.py.",
        }

    _echo(_run("corine", step))


@ingest_app.command("all-demo")
def all_demo(
    fetch_heat: bool = typer.Option(
        False, "--fetch-heat", help="Also fetch Open-Meteo points (waits for quota; can take days)"
    ),
) -> None:
    """Everything for the demo municipalities (Grad Karlovac, Grad Zagreb).

    Sources, municipalities, census grid, action rules, public buildings, heat cells and status. Heat points
    come from `ingest heat-grid` (quota-bound); without them the status stays `unavailable`."""
    from sqlalchemy import text

    from otporno_api.actions import sync_rules
    from otporno_api.exposure import DEMO, compute_municipality
    from otporno_api.ingest.buildings import ingest_buildings
    from otporno_api.ingest.grid import ingest_grid
    from otporno_api.ingest.municipalities import ingest_municipalities
    from otporno_api.ingest.sources import register_all

    def step(session: Session, settings: OtpornoSettings) -> dict[str, Any]:
        out: dict[str, Any] = {}
        register_all(session, settings)
        if not session.scalar(text("select count(*) from municipality")):
            out["municipalities"] = ingest_municipalities(session, settings)
        if not session.scalar(text("select count(*) from cell")):
            out["grid"] = ingest_grid(session, settings)
        out["action_rules"] = sync_rules(session)
        for lau, name in DEMO.items():
            out[name] = {"buildings": ingest_buildings(session, settings, lau)}
        if fetch_heat:
            from otporno_api.heat import run_heat_job
            from otporno_api.om_client import OpenMeteoClient

            client = OpenMeteoClient(settings, make_session_factory(settings))
            try:
                out["heat_job"] = run_heat_job(client, session, lau_ids=list(DEMO))
            finally:
                client.close()
        for lau, name in DEMO.items():
            out[name]["compute"] = compute_municipality(session, lau)
        return out

    _echo(_run("all-demo", step))


@app.command("validate")
def validate(
    out: str = typer.Option(
        "docs/validation_points.csv", help="CSV template for the human check against the HV viewer"
    ),
    seed: int = typer.Option(2026, help="Sampling seed (the same points every run)"),
) -> None:
    """Validation helper: 30 reproducible points in Grad Karlovac for a manual check, plus a heat sanity line.

    Writes a CSV template (columns for what you read in the Hrvatske vode viewer) and prints the modelled
    `base_hot_days` of Zagreb Grič next to a link to the DHMZ climate normals; the link is for you to
    compare by hand, no DHMZ value is reproduced here."""
    from otporno_api.validation import run_validation

    _echo(_run("validate", lambda s, st: run_validation(s, st, out, seed)))


if __name__ == "__main__":  # pragma: no cover
    app()
