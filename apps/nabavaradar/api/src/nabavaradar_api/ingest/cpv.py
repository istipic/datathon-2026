"""CPV 2008 code list (official workbook from the Publications Office, published via TED)."""

from __future__ import annotations

import re
import zipfile
from pathlib import Path
from typing import Any

import openpyxl
import structlog
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from nabavaradar_api.constants import SRC_CPV
from nabavaradar_api.db import Cpv
from nabavaradar_api.settings import NabavaSettings
from opendata_core import http as http_mod
from opendata_core.provenance import record_ingestion

log = structlog.get_logger(__name__)

CPV_URL = "https://ted.europa.eu/documents/d/ted/cpv_2008_xls"
CODE_RE = re.compile(r"^(\d{8})-(\d)$")


def clean(text: Any) -> str | None:
    """Collapse whitespace (the workbook uses non-breaking spaces); empty -> ``None``."""
    if text is None:
        return None
    out = re.sub(r"\s+", " ", str(text).replace("\xa0", " ")).strip()
    return out or None


def read_workbook(path: Path) -> list[dict[str, Any]]:
    """Rows of the 'CPV codes' sheet as dicts (code, check digit, hr/en label, division, group)."""
    wb = openpyxl.load_workbook(path, read_only=True)
    ws = wb["CPV codes"]
    rows = ws.iter_rows(values_only=True)
    header = next(rows)
    hr, en = header.index("HR"), header.index("EN")
    out: list[dict[str, Any]] = []
    for row in rows:
        match = CODE_RE.match(str(row[0] or ""))
        if not match:
            continue
        code, check = match.groups()
        label_en = clean(row[en])
        if not label_en:
            continue
        out.append(
            {
                "code": code,
                "check_digit": check,
                "label_hr": clean(row[hr]),
                "label_en": label_en,
                "division": code[:2],
                "cpv_group": code[:3],
            }
        )
    return out


def ingest_cpv(session: Session, settings: NabavaSettings) -> int:
    """Download (if needed) and load the CPV list; returns the number of codes."""
    raw = settings.raw_dir / "cpv"
    raw.mkdir(parents=True, exist_ok=True)
    zip_path = raw / "cpv_2008_xls.zip"
    with record_ingestion(session, SRC_CPV, CPV_URL) as run:
        with http_mod.make_client(settings) as client:
            _, sha = http_mod.download_file(client, CPV_URL, zip_path)
        with zipfile.ZipFile(zip_path) as zf:
            name = next(n for n in zf.namelist() if n.endswith(".xlsx"))
            zf.extract(name, raw)
        rows = read_workbook(raw / name)
        for i in range(0, len(rows), 2000):
            stmt = insert(Cpv).values(rows[i : i + 2000])
            stmt = stmt.on_conflict_do_update(
                index_elements=[Cpv.code],
                set_={
                    "check_digit": stmt.excluded.check_digit,
                    "label_hr": stmt.excluded.label_hr,
                    "label_en": stmt.excluded.label_en,
                    "division": stmt.excluded.division,
                    "cpv_group": stmt.excluded.cpv_group,
                },
            )
            session.execute(stmt)
        run.rows = len(rows)
        run.sha256 = sha
        run.retrieved_url = CPV_URL
    log.info("cpv_loaded", codes=len(rows), with_hr=sum(1 for r in rows if r["label_hr"]))
    return len(rows)
