"""Parsing of TED Search API notices (see config/ted_fields.yaml for the field mapping).

The API returns *flattened* lists. Alignment rules (measured on real notices, 2026-11-04):

- ``result-lot-identifier``, ``winner-selection-status`` and the received-submissions blocks are
  aligned per **lot**;
- ``winner-name`` and ``tender-lot-identifier`` are aligned per winning **tender**;
- ``winner-identifier`` is de-duplicated per **organisation** (two tenders of the same winner give
  one identifier), so it is mapped to tenders through the unique names in order of appearance.

Whatever cannot be aligned reliably is left empty instead of guessed.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

NUTS3_RE = re.compile(r"^HR\d{3}$")
CPV8_RE = re.compile(r"^\d{8}$")
LANG_PREFERENCE = ("hrv", "eng")
DESCRIPTION_LIMIT = 6000
ID_MAX = 128  # column width of award.lot_id / award.winner_national_id


@dataclass
class ParsedNotice:
    """A notice row plus its award rows (result notices)."""

    row: dict[str, Any]
    awards: list[dict[str, Any]] = field(default_factory=list)


# ---------------------------------------------------------------------------- small helpers


def as_list(value: Any) -> list[Any]:
    """``None`` -> [], scalar -> [scalar], list -> list."""
    if value is None:
        return []
    return value if isinstance(value, list) else [value]


def ml_list(value: Any) -> list[str]:
    """Strings of a multilingual field ``{lang: str | [str]}`` in the preferred language."""
    if isinstance(value, dict):
        for lang in (*LANG_PREFERENCE, *value.keys()):
            if lang in value and value[lang] not in (None, "", []):
                return [str(x) for x in as_list(value[lang])]
        return []
    return [str(x) for x in as_list(value)]


def ml_first(value: Any) -> str | None:
    """First string of a multilingual field (Croatian, else English, else any language)."""
    items = ml_list(value)
    return items[0].strip() if items and items[0].strip() else None


def parse_date(value: Any) -> date | None:
    """``'2026-07-07+02:00'`` -> date."""
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        return date.fromisoformat(value[:10])
    except ValueError:
        return None


def parse_decimal(value: Any) -> Decimal | None:
    """Decimal from a number or numeric string; ``None`` otherwise."""
    if value in (None, ""):
        return None
    try:
        out = Decimal(str(value))
    except InvalidOperation:
        return None
    return out if out.is_finite() else None


def first_nuts3(*lists: Any) -> str | None:
    """First NUTS3 code ``HRxxx`` found in the given list fields."""
    for lst in lists:
        for code in as_list(lst):
            if isinstance(code, str) and NUTS3_RE.match(code):
                return code
    return None


def unique(items: list[str]) -> list[str]:
    """Order-preserving de-duplication."""
    return list(dict.fromkeys(items))


def parse_deadline(dates: Any, times: Any) -> datetime | None:
    """Latest lot deadline (the notice stays open while any lot is open), timezone-aware."""
    d_list, t_list = as_list(dates), as_list(times)
    found: list[datetime] = []
    for i, d in enumerate(d_list):
        day = parse_date(d)
        if day is None:
            continue
        tz = d[10:] if isinstance(d, str) and len(d) > 10 else "+00:00"
        t = t_list[i] if i < len(t_list) else (t_list[0] if t_list else None)
        clock = t if isinstance(t, str) and re.match(r"^\d{2}:\d{2}:\d{2}", t) else None
        text = f"{day.isoformat()}T{clock}" if clock else f"{day.isoformat()}T23:59:59{tz}"
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            continue
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        found.append(dt)
    return max(found) if found else None


def notice_deadline(raw: dict[str, Any]) -> datetime | None:
    """Tender deadline; restricted procedures only carry the deadline for requests to participate."""
    return parse_deadline(
        raw.get("deadline-receipt-tender-date-lot"), raw.get("deadline-receipt-tender-time-lot")
    ) or parse_deadline(
        raw.get("deadline-receipt-request-date-lot"), raw.get("deadline-receipt-request-time-lot")
    )


def deadline_kind(raw: dict[str, Any]) -> str | None:
    """``tender`` or ``request`` (requests to participate, restricted procedures) or ``None``."""
    if raw.get("deadline-receipt-tender-date-lot"):
        return "tender"
    return "request" if raw.get("deadline-receipt-request-date-lot") else None


def pick_link(links: Any, kind: str) -> str | None:
    """Croatian, else English link of kind ``html`` / ``pdf``."""
    group = (links or {}).get(kind) or {}
    return group.get("HRV") or group.get("ENG") or next(iter(group.values()), None)


def slim_raw(raw: dict[str, Any]) -> dict[str, Any]:
    """Raw notice without the 24-language bloat: keep Croatian/English text and two links."""
    out: dict[str, Any] = {}
    for key, value in raw.items():
        if key == "links":
            out[key] = {
                "html": {
                    k: v for k, v in ((value.get("html") or {}).items()) if k in ("HRV", "ENG")
                },
                "pdf": {k: v for k, v in ((value.get("pdf") or {}).items()) if k in ("HRV", "ENG")},
            }
        elif isinstance(value, dict) and value and all(len(k) == 3 and k.islower() for k in value):
            out[key] = {k: v for k, v in value.items() if k in LANG_PREFERENCE} or dict(
                list(value.items())[:1]
            )
        else:
            out[key] = value
    return out


# ---------------------------------------------------------------------------- notices


def parse_value(raw: dict[str, Any]) -> tuple[Decimal | None, str | None]:
    """Estimated value of a competition notice and its currency (procedure level, else lots)."""
    currency = raw.get("estimated-value-cur-proc") or next(
        iter(as_list(raw.get("estimated-value-cur-lot"))), None
    )
    value = parse_decimal(raw.get("estimated-value-proc"))
    if value is None:
        lots = [parse_decimal(v) for v in as_list(raw.get("estimated-value-lot"))]
        if lots and all(v is not None for v in lots):
            value = sum((v for v in lots if v is not None), Decimal(0))
    return value, currency


def parse_notice(raw: dict[str, Any], kind: str) -> ParsedNotice:
    """Parse one TED notice (``kind`` is ``competition`` or ``result``)."""
    cpv = unique([c for c in map(str, as_list(raw.get("classification-cpv"))) if CPV8_RE.match(c)])
    main = next(
        (str(c) for c in as_list(raw.get("main-classification-proc")) if CPV8_RE.match(str(c))),
        None,
    )
    lots = as_list(raw.get("identifier-lot")) or as_list(raw.get("result-lot-identifier"))
    title = ml_first(raw.get("title-proc")) or ml_first(raw.get("notice-title"))
    description = ml_first(raw.get("description-proc"))
    lot_descriptions = unique(ml_list(raw.get("description-lot")))
    if lot_descriptions:
        joined = " ".join(d for d in lot_descriptions if d and d != description)
        description = f"{description or ''} {joined}".strip() or None
    if description:
        description = description[:DESCRIPTION_LIMIT]
    value, currency = parse_value(raw) if kind == "competition" else (None, None)
    row: dict[str, Any] = {
        "pub_no": raw["publication-number"],
        "type": kind,
        "notice_type": raw.get("notice-type") or "",
        "pub_date": parse_date(raw.get("publication-date")),
        "procedure_id": raw.get("procedure-identifier"),
        "buyer_name": ml_first(raw.get("buyer-name")),
        "buyer_nuts": first_nuts3(raw.get("buyer-country-sub")),
        "place_nuts": first_nuts3(
            raw.get("place-of-performance-subdiv-proc"), raw.get("place-of-performance-subdiv-lot")
        ),
        "cpv_codes": cpv,
        "cpv_main": main or (cpv[0] if cpv else None),
        "title": title,
        "description": description,
        "deadline": notice_deadline(raw) if kind == "competition" else None,
        "value_eur": value if currency == "EUR" else None,
        "currency": currency,
        "n_lots": len(lots) or None,
        "url_html": pick_link(raw.get("links"), "html"),
        "url_pdf": pick_link(raw.get("links"), "pdf"),
        "raw": slim_raw(raw),
    }
    awards = parse_awards(raw) if kind == "result" else []
    return ParsedNotice(row=row, awards=awards)


# ---------------------------------------------------------------------------- awards


def received_per_lot(codes: list[Any], values: list[Any], n_lots: int) -> list[int | None]:
    """Number of tenders received per lot from the flattened (type, value) blocks.

    A block starts when a type code repeats one already seen in the current block. If the number of
    blocks does not equal ``n_lots`` the alignment is unreliable and every lot gets ``None``.
    """
    if not codes or len(codes) != len(values):
        return [None] * n_lots
    blocks: list[dict[str, Any]] = []
    seen: set[str] = set()
    for code, value in zip(codes, values, strict=True):
        if not blocks or code in seen:
            blocks.append({})
            seen = set()
        blocks[-1][code] = value
        seen.add(code)
    if len(blocks) != n_lots:
        return [None] * n_lots
    out: list[int | None] = []
    for block in blocks:
        raw_value = block.get("tenders")
        try:
            out.append(int(raw_value) if raw_value is not None else None)
        except (TypeError, ValueError):
            out.append(None)
    return out


def winner_ids_per_tender(names: list[str], ids: list[str]) -> list[str | None]:
    """OIB / national id for each winning tender (see the module docstring)."""
    if not names:
        return []
    if len(ids) == len(names):
        return [i or None for i in ids]
    distinct = unique(names)
    if len(ids) == len(distinct):
        mapping = dict(zip(distinct, ids, strict=True))
        return [mapping[n] or None for n in names]
    return [None] * len(names)


def parse_awards(raw: dict[str, Any]) -> list[dict[str, Any]]:
    """Award rows of a result notice: one per winning tender, or one empty row per lot."""
    pub_no = raw["publication-number"]
    lots = [str(x) for x in as_list(raw.get("result-lot-identifier"))]
    if not lots:
        return []
    statuses = as_list(raw.get("winner-selection-status"))
    statuses = statuses if len(statuses) == len(lots) else [None] * len(lots)
    received = received_per_lot(
        as_list(raw.get("received-submissions-type-code")),
        as_list(raw.get("received-submissions-type-val")),
        len(lots),
    )
    names = ml_list(raw.get("winner-name"))
    tender_lots = [str(x) for x in as_list(raw.get("tender-lot-identifier"))]
    ids = [str(x) for x in as_list(raw.get("winner-identifier"))]
    aligned = bool(names) and len(names) == len(tender_lots)
    winner_ids = winner_ids_per_tender(names, ids) if aligned else []

    by_lot: dict[str, list[tuple[str, str | None]]] = {}
    if aligned:
        for lot, name, wid in zip(tender_lots, names, winner_ids, strict=True):
            by_lot.setdefault(lot, []).append((name, wid))

    # ``result-lot-identifier`` is per lot *result*: a lot with several winners/contracts appears
    # several times. Group by lot; a lot counts as awarded when any of its entries was.
    entries: dict[str, tuple[Any, int | None]] = {}
    for lot, status, rec in zip(lots, statuses, received, strict=True):
        previous = entries.get(lot)
        if previous is None or (status == "selec-w" and previous[0] != "selec-w"):
            entries[lot] = (status, rec if rec is not None or previous is None else previous[1])
    awards: list[dict[str, Any]] = []
    for lot, (status, rec) in entries.items():
        winners = by_lot.get(lot, [])
        if not winners:
            awards.append(_award(pub_no, lot, 0, status, None, None, rec))
            continue
        for seq, (name, wid) in enumerate(winners):
            awards.append(_award(pub_no, lot, seq, status, name, wid, rec))
    return awards


def _award(
    pub_no: str,
    lot: str,
    seq: int,
    status: Any,
    name: str | None,
    wid: str | None,
    received: int | None,
) -> dict[str, Any]:
    return {
        "pub_no": pub_no,
        "lot_id": lot[:ID_MAX],
        "seq": seq,
        "lot_status": str(status)[:16] if status else None,
        "winner_name": name,
        "winner_national_id": wid.strip()[:ID_MAX] if wid else None,
        "received_submissions": received,
    }
