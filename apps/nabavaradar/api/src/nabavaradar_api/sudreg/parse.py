"""Parsing of Sudreg responses into company-level records.

Only OIB, MBS, name, status, county and NKD activities are kept. Anything that could describe a
natural person (``osobe``, ``funkcije``, e-mail addresses, ...) is dropped by construction: the
parser reads named keys instead of copying the response.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from nabavaradar_api.counties import by_code
from nabavaradar_api.oib import is_valid_oib, normalise_oib

MAIN_ACTIVITY_VERSION = "NKD 2007"  # subjekti.glavna_djelatnost uses the NKD 2007 codes (4 digits)
# vrste_postupaka (register code list, verified 2026-11-04): 1 Bez postupka, 2 Stečaj, 3 Likvidacija,
# 4-7 pre-bankruptcy settlement stages. Companies in bankruptcy/liquidation are not stored.
EXCLUDED_PROCEDURES = frozenset({2, 3})
# vrste_pravnih_oblika: 6 = "trgovac pojedinac" (sole trader). Its name is typically a natural
# person's name, so such subjects are never stored or shown (task rule: no natural persons).
SOLE_TRADER_FORM = 6


@dataclass
class CompanyRecord:
    """A company with its NKD activities (company-level data only)."""

    oib: str
    mbs: int
    name: str
    status: int
    county_code: int | None
    nuts3: str | None
    activities: list[tuple[str, str, bool]] = field(
        default_factory=list
    )  # (code, version, is_main)
    snapshot_id: int | None = None
    snapshot_at: datetime | None = None


def nkd_code_from_number(value: int | str) -> str:
    """``1072`` -> ``'10.72'`` (the register stores the main activity as a number)."""
    digits = str(int(value)).zfill(4)
    return f"{digits[:2]}.{digits[2:]}"


def parse_snapshot_time(value: str | None) -> datetime | None:
    """Sudreg timestamps carry no timezone (guide: 'bez oznake zone'); they are local register
    times, stored here as UTC-labelled instants for display only."""
    if not value:
        return None
    try:
        return datetime.fromisoformat(value).replace(tzinfo=UTC)
    except ValueError:
        return None


def county_fields(code: int | None) -> tuple[int | None, str | None]:
    """(county code, NUTS3) for a Sudreg county code; ``(None, None)`` for 0/unknown/foreign."""
    county = by_code(code)
    return (county.code, county.nuts3) if county else (None, None)


def exclusion_reason(body: dict[str, Any]) -> str | None:
    """Why a ``detalji_subjekta`` subject must not be stored/shown (``None`` = fine)."""
    form = ((body.get("pravni_oblik") or {}).get("vrsta_pravnog_oblika") or {}).get("sifra")
    if form == SOLE_TRADER_FORM:
        return "sole_trader"
    if body.get("stecajna_masa") or body.get("likvidacijska_masa"):
        return "estate"
    postupak = body.get("postupak")
    if isinstance(postupak, int):  # bulk table: numeric code
        if postupak in EXCLUDED_PROCEDURES:
            return "bankruptcy_or_liquidation"
    elif isinstance(postupak, dict):  # detalji_subjekta: {"postupak": {"znacenje": "Stečaj"}}
        meaning = str((postupak.get("postupak") or {}).get("znacenje", "")).lower()
        if meaning in {"stečaj", "likvidacija"}:
            return "bankruptcy_or_liquidation"
    return None


def parse_detail(body: dict[str, Any]) -> CompanyRecord | None:
    """Company record from a ``detalji_subjekta`` response (``expand_relations=true``).

    Returns ``None`` when the subject has no valid OIB.
    """
    raw_oib = body.get("oib") if body.get("oib") is not None else body.get("potpuni_oib")
    if raw_oib is None:
        return None
    oib = normalise_oib(raw_oib)
    if not is_valid_oib(oib):
        return None
    name = ((body.get("tvrtka") or {}).get("ime") or "").strip()
    county, nuts3 = county_fields((body.get("sjediste") or {}).get("sifra_zupanije"))
    activities: list[tuple[str, str, bool]] = []
    seen: set[tuple[str, str]] = set()

    def add(code: str, version: str, main: bool) -> None:
        if (code, version) not in seen:
            seen.add((code, version))
            activities.append((code, version, main))

    main_number = body.get("glavna_djelatnost")
    if main_number:
        add(nkd_code_from_number(main_number), MAIN_ACTIVITY_VERSION, True)
    for item in body.get("predmeti_poslovanja") or []:
        nkd = item.get("nacionalna_klasifikacija_djelatnosti") or {}
        if nkd.get("sifra") and nkd.get("verzija"):
            add(str(nkd["sifra"]), str(nkd["verzija"]), False)
    snapshot_id = body.get("_snapshot_id")
    return CompanyRecord(
        oib=oib,
        mbs=int(body["mbs"]),
        name=name,
        status=int(body.get("status", 1)),
        county_code=county,
        nuts3=nuts3,
        activities=activities,
        snapshot_id=int(snapshot_id) if snapshot_id not in (None, "") else None,
        snapshot_at=parse_snapshot_time(body.get("_snapshot_timestamp")),
    )
