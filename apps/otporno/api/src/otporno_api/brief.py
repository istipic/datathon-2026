"""Printable municipal brief (P1): one self-contained HTML page rendered with Jinja2."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader, select_autoescape
from sqlalchemy.orm import Session

from otporno_api import exposure
from otporno_api.actions import actions_for
from otporno_api.constants import BANDS, DEFAULT_WEIGHTS, FLOOD_DISCLAIMER
from otporno_api.format import fmt_int

_ENV = Environment(
    loader=FileSystemLoader(Path(__file__).parent / "templates"),
    autoescape=select_autoescape(["html", "j2"]),
)


def build_brief(session: Session, lau_id: str, now: datetime | None = None) -> str | None:
    """HTML of the brief, or ``None`` for an unknown municipality."""
    ex = exposure.exposure(session, lau_id)
    if ex is None:
        return None
    cells = exposure.cells_geojson(session, lau_id, dict(DEFAULT_WEIGHTS))
    assert cells is not None
    m = ex["municipality"]
    heat = ex["hazards"]["heat"]
    top = sorted(cells["features"], key=lambda f: f["properties"]["priority"], reverse=True)[:8]
    present = [b["band"] for b in heat["bands"] if b["cells"]]
    top_band = max(present, key=BANDS.index) if present else None
    actions = [
        {"title": "poplava", "rows": actions_for(session, "flood", None, "opcina")},
        {"title": "vrućina", "rows": actions_for(session, "heat", top_band, "opcina")},
    ]
    now = now or datetime.now(ZoneInfo("Europe/Zagreb"))
    template = _ENV.get_template("brief.html.j2")
    return template.render(
        m=m,
        generated=now.strftime("%d.%m.%Y. %H:%M"),
        pop_total=fmt_int(m["pop_total"]),
        pop_65p=fmt_int(m["pop_65p"]),
        heat_high_65p=fmt_int(ex["kpis"]["heat_high_pop_65p"])
        if ex["kpis"]["heat_high_pop_65p"] is not None
        else "nije dostupno",
        bands=[
            {
                **b,
                "cells": fmt_int(b["cells"]),
                "pop_total": fmt_int(b["pop_total"]),
                "pop_65p": fmt_int(b["pop_65p"]),
            }
            for b in heat["bands"]
        ],
        without={k: fmt_int(v) for k, v in heat["without_data"].items()},
        top=[
            {
                "cell": f["properties"]["grd_id"].replace("CRS3035RES1000m", ""),
                "pop_total": fmt_int(f["properties"]["pop_total"]),
                "pop_65p": fmt_int(f["properties"]["pop_65p"]),
                "heat_band": f["properties"]["heat_band"],
                "priority": f"{f['properties']['priority']:.1f}".replace(".", ","),
            }
            for f in top
            if f["properties"]["priority"] > 0
        ],
        actions=actions,
        coverage=heat["coverage"],
        flood_disclaimer=FLOOD_DISCLAIMER,
    )
