"""Free places in Zagreb's city kindergartens (CKAN slobodna-mjesta-u-vrticima-...)."""

from __future__ import annotations

import csv
import io
import re
from dataclasses import dataclass
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

import structlog
from sqlalchemy import delete, insert
from sqlalchemy.orm import Session

from blizu_api.constants import SRC_VRTICI_MJESTA
from blizu_api.db import VrticFreePlaces
from blizu_api.manifest import sha256_file
from opendata_core.ckan import CkanClient, newest_resource
from opendata_core.provenance import record_ingestion

log = structlog.get_logger(__name__)

PACKAGE = "slobodna-mjesta-u-vrticima-i-obrtima-za-cuvanje-djece-grada-zagreba"
HEADER_ROWS = 3
_DATE_RE = re.compile(r"STANJE NA DAN\s+(\d{1,2})\.(\d{1,2})\.(\d{4})", re.IGNORECASE)


@dataclass(frozen=True)
class FreePlacesRow:
    """One kindergarten row of the table."""

    district: str
    name: str
    branches: str | None
    jaslice_free: int
    vrtic_free: int
    attrs: dict[str, int]

    @property
    def total_free(self) -> int:
        """Free places in nursery (jaslice) and kindergarten groups together."""
        return self.jaslice_free + self.vrtic_free


def _int(value: str) -> int:
    value = value.strip()
    return int(value) if value.lstrip("-").isdigit() else 0


def parse_free_places(text: str) -> tuple[list[FreePlacesRow], date | None]:
    """Parse the ';' separated table (3 header rows, totals row, title row with the date).

    Returns the kindergarten rows and the snapshot date read from the "STANJE NA DAN d.m.yyyy" line.
    """
    rows = list(csv.reader(io.StringIO(text.lstrip("﻿")), delimiter=";"))
    if len(rows) <= HEADER_ROWS:
        raise ValueError("free-places file has no data rows")
    section_row, age_row, program_row = rows[0], rows[1], rows[2]
    section = age = ""
    keys: list[str] = []
    section_of: list[str] = []
    for col in range(len(program_row)):
        section = (section_row[col].strip() or section) if col < len(section_row) else section
        age = (age_row[col].strip() or age) if col < len(age_row) else age
        keys.append(f"{section}|{age}|{program_row[col].strip()}")
        section_of.append(section)
    jaslice_cols = [c for c, s in enumerate(section_of) if s.upper() == "JASLICE"]
    vrtic_cols = [c for c, s in enumerate(section_of) if s.upper().startswith("VRTI")]
    if not jaslice_cols or not vrtic_cols:
        raise ValueError("free-places header has no JASLICE/VRTIĆ sections")

    out: list[FreePlacesRow] = []
    snapshot: date | None = None
    for row in rows[HEADER_ROWS:]:
        joined = " ".join(row)
        m = _DATE_RE.search(joined)
        if m:
            snapshot = date(int(m[3]), int(m[2]), int(m[1]))
            continue
        name = row[1].strip() if len(row) > 1 else ""
        if not name or name.upper() == "UKUPNO":
            continue
        values = {keys[c]: _int(row[c]) for c in range(3, min(len(row), len(keys)))}
        out.append(
            FreePlacesRow(
                district=row[0].strip(),
                name=name,
                branches=row[2].strip() or None,
                jaslice_free=_int(row[jaslice_cols[-1]]),  # "UKUPNO RED. + POS." of JASLICE
                vrtic_free=_int(row[vrtic_cols[-1]]),  # "UKUPNO RED. + POS." of VRTIĆ
                attrs=values,
            )
        )
    return out, snapshot


def ingest_free_places(session: Session, settings: Any, ckan: CkanClient, today: str) -> int:
    """Download the newest CSV of the package and replace ``vrtic_free_places``."""
    with record_ingestion(session, SRC_VRTICI_MJESTA, f"CKAN {PACKAGE}") as run:
        pkg = ckan.package_show(PACKAGE)
        resource = newest_resource(pkg, ["CSV"])
        if resource is None:
            raise RuntimeError(f"no CSV resource in CKAN package {PACKAGE}")
        raw_dir: Path = settings.raw_dir
        path, sha = ckan.download(resource["url"], raw_dir / f"{today}_zg-vrtici-mjesta.csv")
        rows, snapshot = parse_free_places(path.read_text(encoding="utf-8"))
        run.sha256 = sha256_file(path)
        run.retrieved_url = resource["url"]
        modified = resource.get("last_modified")
        run.source_last_modified = (
            datetime.fromisoformat(modified).replace(tzinfo=UTC) if modified else None
        )
        session.execute(delete(VrticFreePlaces))
        session.execute(
            insert(VrticFreePlaces),
            [
                {
                    "snapshot_date": snapshot.isoformat() if snapshot else None,
                    "district": r.district,
                    "name": r.name,
                    "branches": r.branches,
                    "jaslice_free": r.jaslice_free,
                    "vrtic_free": r.vrtic_free,
                    "total_free": r.total_free,
                    "resource_name": resource.get("name"),
                    "attrs": r.attrs,
                }
                for r in rows
            ],
        )
        run.rows = len(rows)
        log.info(
            "free_places", rows=len(rows), snapshot=str(snapshot), resource=resource.get("name")
        )
    return len(rows)
