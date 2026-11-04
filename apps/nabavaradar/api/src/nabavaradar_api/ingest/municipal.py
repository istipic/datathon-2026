"""P1: municipal contract registers from the open-data portal (CKAN).

``package_search(q='registar ugovora javna nabava', rows=100)``; XLSX/CSV resources are read and their
columns are mapped to {predmet, cpv, bidder (name/OIB), amount, date} by fuzzy header matching. Only
files where at least three of these five fields map are kept. A coverage report lists every file
that was found, parsed or rejected, with the reason.

Privacy: a bidder's *name* is stored only when the bidder is a registered company (its OIB is in
``company`` or the name carries a legal-form suffix). Registers of small buyers often name sole
traders and other natural persons; those names are dropped, the row's other fields are kept.
"""

from __future__ import annotations

import csv
import io
import re
import unicodedata
import zipfile
from collections import Counter
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

import httpx
import openpyxl
import structlog
from rapidfuzz import fuzz
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from nabavaradar_api.constants import SRC_MUNICIPAL
from nabavaradar_api.db import Company, MunicipalContract
from nabavaradar_api.oib import is_valid_oib
from nabavaradar_api.settings import NabavaSettings
from opendata_core import http as http_mod
from opendata_core.ckan import CkanClient
from opendata_core.provenance import record_ingestion

log = structlog.get_logger(__name__)

QUERY = "registar ugovora javna nabava"
MAX_BYTES = 25_000_000
MIN_MAPPED_FIELDS = 3
HEADER_SCAN_ROWS = 15

# canonical header phrases per target field (normalised: lower case, no diacritics/punctuation)
SYNONYMS: dict[str, list[str]] = {
    "predmet": [
        "predmet nabave",
        "predmet ugovora",
        "predmet",
        "opis predmeta nabave",
        "opis nabave",
        "naziv predmeta nabave",
        "predmet javne nabave",
        "opis",
    ],
    "cpv": ["cpv", "cpv oznaka", "cpv kod", "cpv broj", "oznaka cpv", "cpv oznaka predmeta nabave"],
    "bidder": [
        "ponuditelj",
        "naziv ponuditelja",
        "odabrani ponuditelj",
        "dobavljac",
        "naziv dobavljaca",
        "isporucitelj",
        "izvrsitelj",
        "ugovaratelj",
        "gospodarski subjekt",
        "naziv gospodarskog subjekta",
        "naziv i sjediste ponuditelja",
        "naziv i sjediste gospodarskog subjekta",
        "naziv i sjediste izvrsitelja",
        "izvodac",
        "izvodjac",
        "naziv izvodaca",
        "naziv ugovaratelja",
        "naziv ugovorne stranke",
        "ugovorna stranka",
        "ugovorna strana",
        "druga ugovorna strana",
    ],
    "bidder_oib": [
        "oib",
        "oib ponuditelja",
        "oib dobavljaca",
        "oib gospodarskog subjekta",
        "oib izvrsitelja",
        "oib isporucitelja",
        "oib ugovaratelja",
        "oib izvodaca",
    ],
    "amount": [
        "iznos",
        "vrijednost",
        "ukupni iznos",
        "iznos ugovora",
        "vrijednost ugovora",
        "iznos bez pdv a",
        "iznos bez pdv",
        "vrijednost bez pdv a",
        "ukupna vrijednost ugovora",
        "ugovoreni iznos",
        "ugovorena vrijednost",
        "iznos u eur",
        "iznos u kn",
        "iznos s pdv om",
        "ugovoreno s pdv om",
        "ugovoreno bez pdv a",
        "ugovoreno",
        "vrijednost s pdv om",
        "cijena",
    ],
    "date": [
        "datum",
        "datum sklapanja ugovora",
        "datum ugovora",
        "datum sklapanja",
        "datum zakljucenja ugovora",
        "datum potpisa ugovora",
        "datum sklapanja ugovora okvirnog sporazuma",
    ],
}
FIELD_GROUPS = ("predmet", "cpv", "bidder", "amount", "date")  # bidder name or OIB count once
LEGAL_FORM_RE = re.compile(
    r"(\bd\.?\s?o\.?\s?o\b|\bj\.?\s?d\.?\s?o\.?\s?o\b|\bd\.?\s?d\b|\bk\.?\s?d\b|\bj\.?\s?t\.?\s?d\b|"
    r"\bzadruga\b|\bustanova\b|\budruga\b|\bgrad\b|\bopcina\b|\bzupanija\b|\bd\.d\.)",
    re.IGNORECASE,
)


def normalise_header(text: Any) -> str:
    """Lower case, diacritics and punctuation removed, whitespace collapsed (``đ`` -> ``d``)."""
    lowered = str(text or "").lower().replace("đ", "d")  # NFKD does not decompose đ
    raw = unicodedata.normalize("NFKD", lowered).encode("ascii", "ignore").decode()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", raw)).strip()


# a header about the buyer or a subcontractor must never be read as the bidder / its OIB
BIDDER_EXCLUDED_WORDS = ("narucitelj", "podugovarat", "podizvoditelj", "kupac", "narucitelja")
EXACT_SCORE = 100.0
CONTAINS_BASE = 92.0
CONTAINS_FLOOR = 80.0
TYPO_RATIO = 90.0


def phrase_score(header: str, phrase: str) -> float:
    """How well a normalised header matches a synonym phrase (0 = no match).

    - identical: 100;
    - a phrase of >= 2 words that is contained in the header: 92 minus 2 per extra word (min 80),
      because real headers append qualifiers ("... (s PDV-om) u eurima");
    - otherwise a typo-tolerant match (>= 90 % similar);
    - single-word phrases ("datum", "iznos", "oib") only match identically, so "Datum izvršenja" or
      "Iznos PDV-a" are not mistaken for the contract date or amount.
    """
    if header == phrase:
        return EXACT_SCORE
    h_words, p_words = header.split(), phrase.split()
    if len(p_words) >= 2 and set(p_words) <= set(h_words):
        return max(CONTAINS_FLOOR, CONTAINS_BASE - 2.0 * (len(h_words) - len(p_words)))
    ratio = fuzz.ratio(header, phrase)
    return float(ratio) if ratio >= TYPO_RATIO else 0.0


def map_headers(headers: list[Any]) -> dict[str, int]:
    """Column index per target field, by matching the headers against the synonym phrases.

    Each header is used for at most one field; a field takes its best-scoring header (the leftmost
    on ties). Fields: predmet, cpv, bidder, bidder_oib, amount, date.
    """
    norm = [normalise_header(h) for h in headers]
    candidates: list[tuple[float, int, str]] = []
    for field_name, phrases in SYNONYMS.items():
        for idx, header in enumerate(norm):
            if not header:
                continue
            lead = " ".join(header.split()[:2])  # "OIB naručitelja", "Naziv podugovaratelja", ...
            if field_name in ("bidder", "bidder_oib") and any(
                w in lead for w in BIDDER_EXCLUDED_WORDS
            ):
                continue
            score = max((phrase_score(header, ph) for ph in phrases), default=0.0)
            if score >= CONTAINS_FLOOR:
                candidates.append((score, -idx, field_name))
    mapping: dict[str, int] = {}
    used: set[int] = set()
    for _score, neg_idx, field_name in sorted(candidates, reverse=True):
        idx = -neg_idx
        if field_name not in mapping and idx not in used:
            mapping[field_name] = idx
            used.add(idx)
    return mapping


def mapped_groups(mapping: dict[str, int]) -> int:
    """Number of the five field groups that mapped (bidder name and OIB count as one)."""
    return sum(
        1 for g in FIELD_GROUPS if g in mapping or (g == "bidder" and "bidder_oib" in mapping)
    )


def parse_amount(value: Any) -> Decimal | None:
    """Number from a cell: ``1.234,56``, ``1234.56``, ``1 234,56 EUR`` -> Decimal."""
    if value is None or value == "":
        return None
    if isinstance(value, int | float | Decimal):
        return Decimal(str(value))
    text = re.sub(r"[^\d,.\-]", "", str(value).replace("\xa0", " "))
    if not re.search(r"\d", text):
        return None
    if "," in text and "." in text:
        text = (
            text.replace(".", "").replace(",", ".")
            if text.rfind(",") > text.rfind(".")
            else text.replace(",", "")
        )
    elif "," in text:
        text = text.replace(",", ".")
    elif text.count(".") > 1:
        text = text.replace(".", "")
    try:
        return Decimal(text)
    except InvalidOperation:
        return None


def parse_date(value: Any) -> date | None:
    """Date from a datetime cell or ``dd.mm.yyyy`` / ``yyyy-mm-dd`` text."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    text = str(value or "").strip()
    for pattern, order in (
        (r"(\d{1,2})\.\s?(\d{1,2})\.\s?(\d{4})", "dmy"),
        (r"(\d{4})-(\d{2})-(\d{2})", "ymd"),
    ):
        m = re.search(pattern, text)
        if m:
            a, b, c = (int(x) for x in m.groups())
            try:
                return date(c, b, a) if order == "dmy" else date(a, b, c)
            except ValueError:
                return None
    return None


def clean_cpv(value: Any) -> str | None:
    """First 8-digit CPV code in a cell (check digit allowed), else a 2-8 digit prefix."""
    m = re.search(r"\b(\d{8})(?:-\d)?\b", str(value or ""))
    if m:
        return m.group(1)
    m = re.match(r"^\s*(\d{2,8})\s*$", str(value or ""))
    return m.group(1) if m else None


def is_company_name(name: str) -> bool:
    """True when the name carries a legal-form marker (d.o.o., d.d., ...), i.e. is not a person."""
    return bool(
        LEGAL_FORM_RE.search(normalise_header(name).replace(" ", " ")) or LEGAL_FORM_RE.search(name)
    )


# ---------------------------------------------------------------------------- reading files


def read_table(path: Path, fmt: str) -> list[list[Any]]:
    """All rows of the first sheet that yields a usable header (XLSX) or of a CSV file."""
    if "csv" in fmt:
        raw = path.read_bytes()
        for enc in ("utf-8-sig", "cp1250", "latin-1"):
            try:
                text = raw.decode(enc)
                break
            except UnicodeDecodeError:
                continue
        try:
            dialect = csv.Sniffer().sniff(text[:4096], delimiters=";,\t|")
        except csv.Error:
            dialect = csv.excel
            dialect.delimiter = ";"  # type: ignore[misc]
        return [list(r) for r in csv.reader(io.StringIO(text), dialect)]
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    best: list[list[Any]] = []
    for ws in wb.worksheets:
        rows = [list(r) for r in ws.iter_rows(values_only=True)]
        if len(rows) > len(best):
            best = rows
    return best


def find_header(rows: list[list[Any]]) -> tuple[int, dict[str, int]]:
    """Index of the header row (best mapping within the first rows) and its column mapping."""
    best_idx, best_map = -1, {}
    for i, row in enumerate(rows[:HEADER_SCAN_ROWS]):
        mapping = map_headers(row)
        if mapped_groups(mapping) > mapped_groups(best_map):
            best_idx, best_map = i, mapping
    return best_idx, best_map


@dataclass
class FileReport:
    """Outcome for one resource."""

    resource_id: str
    package: str
    url: str
    fmt: str
    status: str  # parsed | rejected
    reason: str | None = None
    rows: int = 0
    mapped: dict[str, int] = field(default_factory=dict)


def extract_rows(
    rows: list[list[Any]], header_idx: int, mapping: dict[str, int]
) -> list[dict[str, Any]]:
    """Contract rows below the header (empty rows skipped)."""
    out: list[dict[str, Any]] = []

    def cell(row: list[Any], key: str) -> Any:
        i = mapping.get(key)
        return row[i] if i is not None and i < len(row) else None

    for row in rows[header_idx + 1 :]:
        if not any(str(c).strip() for c in row if c is not None):
            continue
        bidder_cell = str(cell(row, "bidder") or "")
        oib_raw = re.sub(r"\D", "", str(cell(row, "bidder_oib") or ""))
        if not is_valid_oib(oib_raw):  # many registers write "... OIB: 12345678901" inside the cell
            found = re.search(r"OIB\D{0,5}(\d{11})", bidder_cell, re.IGNORECASE)
            oib_raw = found.group(1) if found else ""
        oib = oib_raw if is_valid_oib(oib_raw) else None
        predmet = str(cell(row, "predmet") or "").strip() or None
        record = {
            "predmet": predmet[:2000] if predmet else None,
            "cpv": clean_cpv(cell(row, "cpv")),
            "bidder": (bidder_cell.strip().splitlines() or [""])[0].strip(" ,;") or None,
            "bidder_oib": oib,
            "amount": parse_amount(cell(row, "amount")),
            "contract_date": parse_date(cell(row, "date")),
        }
        if any(record[k] for k in ("predmet", "cpv", "bidder", "bidder_oib", "amount")):
            out.append(record)
    return out


def ingest_municipal(session: Session, settings: NabavaSettings) -> dict[str, Any]:
    """Search CKAN, read XLSX/CSV registers and store the mapped rows; returns the coverage report."""
    raw_dir = settings.raw_dir / "municipal"
    raw_dir.mkdir(parents=True, exist_ok=True)
    known = {o for (o,) in session.execute(select(Company.oib))}
    reports: list[FileReport] = []
    stored = 0
    with record_ingestion(session, SRC_MUNICIPAL, f"CKAN package_search q='{QUERY}'") as run:
        with http_mod.make_client(settings) as client:
            ckan = CkanClient(settings, client=client)
            packages = ckan.package_search(QUERY, rows=100)["results"]
            for pkg in packages:
                title = pkg.get("title") or pkg["name"]
                for res in pkg.get("resources", []):
                    fmt = (res.get("format") or "").lower()
                    rep = FileReport(res["id"], title, res.get("url") or "", fmt, "rejected")
                    reports.append(rep)
                    if not ("xlsx" in fmt or "csv" in fmt):
                        rep.reason = f"unsupported format '{fmt or 'none'}'"
                        continue
                    if not rep.url:
                        rep.reason = "no download url"
                        continue
                    ext = "csv" if "csv" in fmt else "xlsx"
                    dest = raw_dir / f"{res['id']}.{ext}"
                    try:
                        path, _sha = ckan.download(rep.url, dest)
                        if path.stat().st_size > MAX_BYTES:
                            rep.reason = "file too large"
                            continue
                        table = read_table(path, fmt)
                    except zipfile.BadZipFile:
                        rep.reason = "unreadable: not a valid XLSX file (HTML page or legacy XLS)"
                        continue
                    except httpx.HTTPStatusError as exc:
                        rep.reason = (
                            f"unreadable: download failed (HTTP {exc.response.status_code})"
                        )
                        continue
                    except Exception as exc:  # noqa: BLE001 - a broken file must not stop the run
                        rep.reason = f"unreadable: {type(exc).__name__}"
                        continue
                    idx, mapping = find_header(table)
                    rep.mapped = mapping
                    if idx < 0 or mapped_groups(mapping) < MIN_MAPPED_FIELDS:
                        rep.reason = f"only {mapped_groups(mapping)} of 5 fields mapped (need {MIN_MAPPED_FIELDS})"
                        continue
                    rows = extract_rows(table, idx, mapping)
                    for r in rows:
                        r["package"] = title
                        r["source_id"] = res["id"]
                        known_company = r["bidder_oib"] in known if r["bidder_oib"] else False
                        if r["bidder"] and not (known_company or is_company_name(r["bidder"])):
                            r["bidder"] = None  # possibly a natural person: name not stored
                    session.execute(
                        delete(MunicipalContract).where(MunicipalContract.source_id == res["id"])
                    )
                    session.add_all(MunicipalContract(**r) for r in rows)
                    session.commit()
                    rep.status, rep.rows = "parsed", len(rows)
                    stored += len(rows)
        # rows of resources that are no longer parsed (rejected now, or gone from CKAN) are removed
        parsed_ids = [r.resource_id for r in reports if r.status == "parsed"]
        session.execute(delete(MunicipalContract).where(MunicipalContract.source_id.not_in(parsed_ids)))
        session.commit()
        run.rows = stored
    reasons =Counter(r.reason.split(":")[0].split(" (")[0] for r in reports if r.reason)
    summary = {
        "query": QUERY,
        "packages": len(packages),
        "files_found": len(reports),
        "files_parsed": sum(1 for r in reports if r.status == "parsed"),
        "files_rejected": sum(1 for r in reports if r.status == "rejected"),
        "rejected_by_reason": dict(reasons),
        "rows_stored": stored,
        "files": [
            {
                "resource": r.resource_id,
                "package": r.package,
                "format": r.fmt,
                "status": r.status,
                "reason": r.reason,
                "rows": r.rows,
                "mapped": sorted(r.mapped),
            }
            for r in reports
        ],
    }
    log.info("municipal_loaded", **{k: v for k, v in summary.items() if k != "files"})
    return summary
