"""TED notice ingestion (Search API v3, anonymous, ITERATION pagination, upsert by publication number).

Windows (task): competition notices of the last 120 days, result notices of the last 36 months.
A re-run is idempotent; unless ``full`` is set it only re-reads notices published since a week
before the newest stored one, so the daily cron job is cheap.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from typing import Any

import httpx
import structlog
import yaml
from sqlalchemy import case, delete, func, null, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from nabavaradar_api.constants import (
    COMPETITION_NOTICE_TYPES,
    RESULT_NOTICE_TYPES,
    SRC_TED_COMPETITION,
    SRC_TED_RESULT,
)
from nabavaradar_api.counties import CONFIG_DIR
from nabavaradar_api.db import Award, Notice
from nabavaradar_api.ingest.ted_parse import ParsedNotice, parse_notice
from nabavaradar_api.settings import NabavaSettings
from opendata_core import http as http_mod
from opendata_core.provenance import record_ingestion

log = structlog.get_logger(__name__)

PAGE_LIMIT = 250  # API maximum per page
MAX_FIELDS_PER_PAGE = 10_000  # API maximum (limit x number of fields)
OVERLAP_DAYS = 7
PAUSE_S = 0.25


def load_fields(kind: str) -> list[str]:
    """TED field names to request for ``kind``, taken from config/ted_fields.yaml."""
    spec = yaml.safe_load((CONFIG_DIR / "ted_fields.yaml").read_text(encoding="utf-8"))["fields"]
    fields = [
        f["ted_field"]
        for f in spec.values()
        if kind in f["applies_to"] and f["ted_field"] != "links"
    ]
    if PAGE_LIMIT * len(fields) > MAX_FIELDS_PER_PAGE:
        raise ValueError(f"{len(fields)} fields x {PAGE_LIMIT} notices exceeds the API page budget")
    return fields


def build_query(kind: str, since: date) -> str:
    """Expert-search query: buyer country ISO alpha-3, dates as YYYYMMDD."""
    types = COMPETITION_NOTICE_TYPES if kind == "competition" else RESULT_NOTICE_TYPES
    return (
        f"buyer-country=HRV AND notice-type IN ({' '.join(types)}) "
        f"AND publication-date>={since.strftime('%Y%m%d')}"
    )


def iterate(
    client: httpx.Client, settings: NabavaSettings, query: str, fields: list[str]
) -> Iterator[list[dict[str, Any]]]:
    """Pages of notices in ITERATION mode (the token of each response feeds the next request)."""
    token: str | None = None
    while True:
        body: dict[str, Any] = {
            "query": query,
            "fields": fields,
            "limit": PAGE_LIMIT,
            "scope": "ALL",
            "paginationMode": "ITERATION",
        }
        if token:
            body["iterationNextToken"] = token
        data = http_mod.post_json(client, settings.ted_search_url, body)
        notices = data.get("notices") or []
        if not notices:
            return
        yield notices
        token = data.get("iterationNextToken")
        if not token:
            return
        time.sleep(PAUSE_S)


def window_start(kind: str, settings: NabavaSettings, today: date) -> date:
    """Start of the ingest window for ``kind``."""
    if kind == "competition":
        return today - timedelta(days=settings.competition_days)
    return today - timedelta(days=round(settings.result_months * 30.4375))


def _since(session: Session, kind: str, start: date, full: bool) -> date:
    if full:
        return start
    newest = session.scalar(select(func.max(Notice.pub_date)).where(Notice.type == kind))
    return max(start, newest - timedelta(days=OVERLAP_DAYS)) if newest else start


def upsert_notices(session: Session, parsed: list[ParsedNotice]) -> None:
    """Upsert notices and replace their awards (keeps embeddings of unchanged text)."""
    parsed = list({p.row["pub_no"]: p for p in parsed}.values())  # one row per notice per statement
    rows = [p.row for p in parsed]
    if not rows:
        return
    stmt = insert(Notice).values(rows)
    keep = {"pub_no", "embedding"}
    update = {
        c.name: getattr(stmt.excluded, c.name)
        for c in Notice.__table__.columns
        if c.name not in keep
    }
    update["embedding"] = case(
        (
            or_(
                Notice.title.is_distinct_from(stmt.excluded.title),
                Notice.description.is_distinct_from(stmt.excluded.description),
                Notice.cpv_codes.is_distinct_from(stmt.excluded.cpv_codes),
            ),
            null(),
        ),
        else_=Notice.embedding,
    )
    session.execute(stmt.on_conflict_do_update(index_elements=[Notice.pub_no], set_=update))
    pub_nos = [r["pub_no"] for r in rows]
    session.execute(delete(Award).where(Award.pub_no.in_(pub_nos)))
    awards = [a for p in parsed for a in p.awards]
    for i in range(0, len(awards), 5000):
        session.execute(insert(Award).values(awards[i : i + 5000]))


def ingest_kind(
    session: Session,
    settings: NabavaSettings,
    client: httpx.Client,
    kind: str,
    *,
    today: date,
    full: bool = False,
) -> dict[str, Any]:
    """Ingest one kind of notices; returns counts."""
    source = SRC_TED_COMPETITION if kind == "competition" else SRC_TED_RESULT
    start = window_start(kind, settings, today)
    since = _since(session, kind, start, full)
    query = build_query(kind, since)
    fields = load_fields(kind)
    seen = awards = 0
    with record_ingestion(session, source, f"{settings.ted_search_url} :: {query}") as run:
        for page in iterate(client, settings, query, fields):
            parsed = [parse_notice(n, kind) for n in page]
            upsert_notices(session, parsed)
            session.commit()  # progress survives a failure later in the run
            seen += len(parsed)
            awards += sum(len(p.awards) for p in parsed)
            log.info("ted_page", kind=kind, notices=seen, awards=awards)
        stored = session.scalar(select(func.count()).select_from(Notice).where(Notice.type == kind))
        newest = session.scalar(select(func.max(Notice.pub_date)).where(Notice.type == kind))
        run.rows = stored
        if newest:
            run.source_last_modified = datetime.combine(newest, datetime.min.time(), tzinfo=UTC)
    return {
        "kind": kind,
        "since": since.isoformat(),
        "fetched": seen,
        "awards": awards,
        "stored": stored,
    }


def ingest_ted(
    session: Session,
    settings: NabavaSettings,
    *,
    kinds: tuple[str, ...] = ("competition", "result"),
    full: bool = False,
    today: date | None = None,
) -> list[dict[str, Any]]:
    """Ingest competition and/or result notices."""
    today = today or datetime.now(UTC).date()
    reports = []
    with http_mod.make_client(settings) as client:
        client.headers["Content-Type"] = "application/json"
        for kind in kinds:
            reports.append(ingest_kind(session, settings, client, kind, today=today, full=full))
    return reports
