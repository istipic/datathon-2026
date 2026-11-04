"""``nabavaradar`` command line: ingestion steps, validation and scheduled jobs."""

from __future__ import annotations

import json
import time
from collections.abc import Callable
from typing import Any

import structlog
import typer
from sqlalchemy.orm import Session

from nabavaradar_api.db import make_session_factory
from nabavaradar_api.settings import NabavaSettings, get_settings
from opendata_core.logging import configure_logging

app = typer.Typer(help="NabavaRadar: ingestion, validation, digest", no_args_is_help=True)
ingest_app = typer.Typer(help="Load data sources and derive artefacts", no_args_is_help=True)
app.add_typer(ingest_app, name="ingest")

log = structlog.get_logger("nabavaradar.cli")

Step = Callable[[Session, NabavaSettings], Any]


def _run(name: str, step: Step) -> Any:
    settings = get_settings()
    configure_logging(settings)
    if not settings.database_url:
        raise typer.BadParameter("DATABASE_URL is not set (see apps/nabavaradar/.env.example)")
    if not settings.contact_email:
        raise typer.BadParameter(
            "CONTACT_EMAIL is not set: external sources need an identifying User-Agent"
        )
    t0 = time.time()
    with make_session_factory(settings)() as session:
        result = step(session, settings)
    log.info("step_done", step=name, seconds=round(time.time() - t0, 1))
    return result


@ingest_app.command("sources")
def sources() -> None:
    """Register all data sources."""
    from nabavaradar_api.ingest.sources import register_all

    _run("sources", register_all)


@ingest_app.command("cpv")
def cpv() -> None:
    """Load the official CPV 2008 list (Croatian labels)."""
    from nabavaradar_api.ingest.cpv import ingest_cpv

    _run("cpv", ingest_cpv)


@ingest_app.command("sudreg")
def sudreg(
    snapshot_id: int | None = typer.Option(None, help="Pin a snapshot (default: freshest)"),
) -> None:
    """Bulk-load companies, NKD codes and activities from the register (one pinned snapshot)."""
    from nabavaradar_api.ingest.sudreg_bulk import ingest_sudreg

    report = _run("sudreg", lambda s, st: ingest_sudreg(s, st, snapshot_id=snapshot_id))
    typer.echo(json.dumps(report, indent=2, ensure_ascii=False))


@ingest_app.command("ted")
def ted(
    full: bool = typer.Option(False, help="Re-read the whole window instead of the last week"),
    kind: str = typer.Option("both", help="competition | result | both"),
) -> None:
    """Load TED competition (last 120 days) and result (last 36 months) notices."""
    from nabavaradar_api.ingest.ted import ingest_ted

    kinds = ("competition", "result") if kind == "both" else (kind,)
    reports = _run("ted", lambda s, st: ingest_ted(s, st, kinds=kinds, full=full))
    typer.echo(json.dumps(reports, indent=2, ensure_ascii=False))


@ingest_app.command("municipal")
def municipal() -> None:
    """P1: load municipal contract registers (CKAN, XLSX/CSV) and report coverage."""
    from sqlalchemy.dialects.postgresql import insert

    from nabavaradar_api.db import Calibration
    from nabavaradar_api.ingest.municipal import ingest_municipal

    def step(session: Session, settings: NabavaSettings) -> dict[str, Any]:
        summary = ingest_municipal(session, settings)
        stmt = insert(Calibration).values(
            key="municipal_coverage", value=json.loads(json.dumps(summary, default=str))
        )
        session.execute(
            stmt.on_conflict_do_update(
                index_elements=[Calibration.key], set_={"value": stmt.excluded.value}
            )
        )
        session.commit()
        return summary

    summary = _run("municipal", step)
    typer.echo(
        json.dumps({k: v for k, v in summary.items() if k != "files"}, indent=2, ensure_ascii=False)
    )


@ingest_app.command("embed")
def embed() -> None:
    """Embed NKD labels, CPV labels and notices (multilingual-e5-small)."""
    from nabavaradar_api.ingest.embed import embed_all

    typer.echo(json.dumps(_run("embed", embed_all), indent=2))


@ingest_app.command("crosswalk")
def crosswalk() -> None:
    """Recompute the NKD -> CPV crosswalk."""
    from nabavaradar_api.ingest.crosswalk import compute_crosswalk

    typer.echo(json.dumps(_run("crosswalk", lambda s, st: compute_crosswalk(s)), indent=2))


@ingest_app.command("calibrate")
def calibrate() -> None:
    """Store the 5th/95th percentile of activity-notice cosines (rescales S)."""
    from nabavaradar_api.ingest.crosswalk import compute_calibration

    typer.echo(json.dumps(_run("calibrate", compute_calibration), indent=2))


@ingest_app.command("stats")
def stats() -> None:
    """Recompute competition statistics per CPV group and NUTS2."""
    from nabavaradar_api.ingest.stats import compute_competition_stats

    typer.echo(json.dumps(_run("stats", compute_competition_stats), indent=2))


@ingest_app.command("derive")
def derive() -> None:
    """embed + crosswalk + calibrate + stats (after sudreg/ted/cpv are loaded)."""
    from nabavaradar_api.ingest.crosswalk import compute_calibration, compute_crosswalk
    from nabavaradar_api.ingest.embed import embed_all
    from nabavaradar_api.ingest.stats import compute_competition_stats

    def step(session: Session, settings: NabavaSettings) -> dict[str, Any]:
        return {
            "embed": embed_all(session, settings),
            "crosswalk": compute_crosswalk(session),
            "calibration": compute_calibration(session, settings),
            "stats": compute_competition_stats(session, settings),
        }

    typer.echo(json.dumps(_run("derive", step), indent=2, default=str))


@app.command("eval")
def evaluate(
    from_stored: bool = typer.Option(
        False, "--from-stored", help="Only re-render docs/validation.md and config/market.yaml from the stored result"
    ),
) -> None:
    """Validate against real winners: recall@10/@20, full-text baseline, tau. Writes docs/validation.md."""
    from pathlib import Path

    from nabavaradar_api.db import Calibration
    from nabavaradar_api.evaluation import EVAL_KEY, run_evaluation, store_evaluation
    from nabavaradar_api.validation_report import write_outputs

    def step(session: Session, settings: NabavaSettings) -> dict[str, Any]:
        if from_stored:
            row = session.get(Calibration, EVAL_KEY)
            if row is None:
                raise typer.BadParameter("no stored evaluation: run `nabavaradar eval` first")
            result = dict(row.value)
        else:
            result = run_evaluation(session)
            store_evaluation(session, result)
        write_outputs(result, Path("apps/nabavaradar/docs/validation.md"))
        return result

    result = _run("eval", step)
    summary = {k: result[k] for k in ("mode", "n", "n_scored", "fit", "fts_baseline", "random_baseline", "window")}
    summary["tau"] = {k: result["tau"].get(k) for k in ("tau", "f1", "precision", "recall", "winners")}
    typer.echo(json.dumps(summary, indent=2, default=str))


digest_app = typer.Typer(help="Weekly e-mail digest", no_args_is_help=True)
app.add_typer(digest_app, name="digest")


@digest_app.command("send")
def digest_send(
    dry_run: bool = typer.Option(False, help="Compute but do not send or update last_sent_at"),
) -> None:
    """Send the weekly digest to every confirmed subscription (cron: Monday 07:00)."""
    from nabavaradar_api.match import MatchEngine
    from nabavaradar_api.subscriptions import send_digests
    from opendata_core import semantic

    def step(session: Session, settings: NabavaSettings) -> dict[str, int]:
        return send_digests(
            session, settings, MatchEngine(), semantic.encode_queries, dry_run=dry_run
        )

    typer.echo(json.dumps(_run("digest", step)))


if __name__ == "__main__":  # pragma: no cover
    app()
