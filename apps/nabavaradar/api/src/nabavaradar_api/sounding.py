"""Market sounding for public buyers: CPV suggestions, capable suppliers by county, competition."""

from __future__ import annotations

import re
import threading
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import numpy as np
import yaml
from numpy.typing import NDArray
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from nabavaradar_api.advice import build_advice
from nabavaradar_api.counties import CONFIG_DIR, by_code, counties
from nabavaradar_api.db import Company, CompetitionStat, Cpv
from nabavaradar_api.ingest.stats import NATIONAL, competition_flag
from opendata_core.provenance import IngestionRun as _Run
from opendata_core.provenance import RunStatus

CPV_RE = re.compile(r"^(\d{8}(-\d)?|\d{2,8})$")
MAX_TEXT = 2000
DEFAULT_TAU = 0.80  # used only until `nabavaradar eval` has written config/market.yaml
SUGGESTIONS = 8


def market_config() -> dict[str, Any]:
    """``config/market.yaml`` written by ``nabavaradar eval`` (tau chosen on the validation set)."""
    path = CONFIG_DIR / "market.yaml"
    if path.exists():
        data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        if data.get("tau") is not None:
            return {**data, "calibrated": True}
    return {"tau": DEFAULT_TAU, "calibrated": False}


def normalise_cpv(value: str) -> str:
    """Digits of a CPV code or prefix (check digit removed): ``'03000000-1'`` -> ``'03000000'``."""
    return value.split("-")[0]


def effective_prefix(value: str) -> str:
    """The level a CPV input stands for: an 8-digit code loses its trailing zeros
    (``45000000`` -> ``45`` division, ``45200000`` -> ``452`` group, ``45214200`` -> ``4521420``);
    shorter inputs are explicit prefixes and are kept. At least two digits remain."""
    digits = normalise_cpv(value)
    if len(digits) == 8:
        stripped = digits.rstrip("0")
        return stripped if len(stripped) >= 2 else digits[:2]
    return digits


@dataclass
class CpvIndex:
    """All CPV labels and embeddings in memory (about 14 MB)."""

    codes: list[str]
    labels: list[str]
    emb: NDArray[np.float32]

    @classmethod
    def load(cls, session: Session) -> CpvIndex:
        rows = session.execute(
            select(Cpv.code, Cpv.label_hr, Cpv.label_en, Cpv.embedding).where(
                Cpv.embedding.is_not(None)
            )
        ).all()
        return cls(
            [r.code for r in rows],
            [r.label_hr or r.label_en for r in rows],
            np.stack([np.asarray(r.embedding, dtype=np.float32) for r in rows])
            if rows
            else np.zeros((0, 384), dtype=np.float32),
        )

    def suggest(self, vec: NDArray[np.float32], k: int = SUGGESTIONS) -> list[dict[str, Any]]:
        """Top-``k`` CPV codes for an (already embedded) query."""
        if not len(self.codes):
            return []
        sims = self.emb @ vec
        order = np.argsort(-sims)[:k]
        return [
            {
                "code": self.codes[i],
                "label": self.labels[i],
                "similarity": round(float(sims[i]), 4),
                "division": self.codes[i][:2],
                "group": self.codes[i][:3],
            }
            for i in order
        ]


_index_lock = threading.Lock()
_index: CpvIndex | None = None


def cpv_index(session: Session) -> CpvIndex:
    """Process-wide CPV index (loaded on first use)."""
    global _index
    with _index_lock:
        if _index is None:
            _index = CpvIndex.load(session)
        return _index


def label_for_prefix(session: Session, prefix: str) -> str | None:
    """Croatian label of the CPV code ``prefix`` padded with zeros (e.g. ``'45'`` -> division)."""
    code = prefix.ljust(8, "0")
    row = session.execute(select(Cpv.label_hr, Cpv.label_en).where(Cpv.code == code)).first()
    if row is None:
        row = session.execute(
            select(Cpv.label_hr, Cpv.label_en)
            .where(Cpv.code.like(f"{prefix}%"))
            .order_by(Cpv.code)
            .limit(1)
        ).first()
    return (row.label_hr or row.label_en) if row else None


def suppliers_by_county(session: Session, division: str, tau: float) -> dict[int | None, int]:
    """Active companies with any activity whose crosswalk similarity to ``division`` is >= tau."""
    rows = session.execute(
        text(
            """
            SELECT c.county_code, count(DISTINCT c.oib) AS n
            FROM company c
            JOIN company_activity a ON a.oib = c.oib
            JOIN crosswalk x ON x.nkd_code = a.nkd_code AND x.nkd_version = a.nkd_version
                 AND x.cpv_level = 'division' AND x.cpv_prefix = :division AND x.similarity >= :tau
            GROUP BY c.county_code
            """
        ),
        {"division": division, "tau": tau},
    ).all()
    return {r.county_code: int(r.n) for r in rows}


def competition_for(session: Session, group: str | None, nuts2: str | None) -> dict[str, Any]:
    """Competition statistics of a CPV group: the NUTS2 region when it has a row, else national."""
    empty: dict[str, Any] = {
        "cpv_group": group,
        "scope": None,
        "n": 0,
        "median_submissions": None,
        "single_bid_share": None,
        "flag": False,
        "window_start": None,
        "window_end": None,
    }
    if not group:
        return empty
    for scope in (nuts2, NATIONAL):
        if not scope:
            continue
        stat = session.get(CompetitionStat, (group, scope))
        if stat:
            share = float(stat.single_bid_share) if stat.single_bid_share is not None else None
            return {
                "cpv_group": group,
                "scope": scope,
                "n": stat.n_awards,
                "median_submissions": float(stat.median_submissions)
                if stat.median_submissions is not None
                else None,
                "single_bid_share": share,
                "flag": competition_flag(stat.n_awards, share),
                "window_start": stat.window_start.isoformat(),
                "window_end": stat.window_end.isoformat(),
            }
    return empty


def data_dates(session: Session) -> dict[str, str | None]:
    """When the underlying data was retrieved / how old it is (never present stale data as live)."""
    out: dict[str, str | None] = {}
    for key, source in (
        ("sudreg", "sudreg"),
        ("ted_result", "ted-result"),
        ("ted_competition", "ted-competition"),
    ):
        run = session.scalars(
            select(_Run)
            .where(_Run.source_id == source, _Run.status == RunStatus.ok)
            .order_by(_Run.finished_at.desc())
            .limit(1)
        ).first()
        out[f"{key}_retrieved_at"] = (
            run.finished_at.isoformat() if run and run.finished_at else None
        )
        out[f"{key}_data_as_of"] = (
            run.source_last_modified.isoformat() if run and run.source_last_modified else None
        )
    return out


def sound_market(
    session: Session,
    *,
    text_input: str | None,
    cpv: str | None,
    county: int | None,
    encode: Any = None,
) -> dict[str, Any]:
    """Market sounding for a planned tender (free text or CPV code/prefix) and a county."""
    cfg = market_config()
    tau = float(cfg["tau"])
    suggestions: list[dict[str, Any]] = []
    if cpv:
        prefix = effective_prefix(cpv)
        label = label_for_prefix(session, prefix)
        suggestions = [
            {
                "code": prefix.ljust(8, "0"),
                "label": label,
                "similarity": None,
                "division": prefix[:2],
                "group": prefix[:3] if len(prefix) >= 3 else None,
            }
        ]
        division = prefix[:2]
        group = prefix[:3] if len(prefix) >= 3 else None
    else:
        from opendata_core import semantic

        vec = (encode or semantic.encode_queries)([text_input or ""])[0]
        suggestions = cpv_index(session).suggest(vec)
        if not suggestions:
            raise RuntimeError("CPV embeddings are missing: run `nabavaradar ingest derive`")
        division, group = suggestions[0]["division"], suggestions[0]["group"]

    county_obj = by_code(county)
    nuts2 = county_obj.nuts2 if county_obj else None
    if group is None:  # only a division was given: use its busiest group nationally
        row = session.execute(
            select(CompetitionStat.cpv_group)
            .where(
                CompetitionStat.nuts2 == NATIONAL, CompetitionStat.cpv_group.like(f"{division}%")
            )
            .order_by(CompetitionStat.n_awards.desc())
            .limit(1)
        ).first()
        group = row.cpv_group if row else None
    comp = competition_for(session, group, nuts2)
    national = competition_for(session, group, None)

    counts = suppliers_by_county(session, division, tau)
    by_county = [
        {
            "county_code": c.code,
            "county": c.name,
            "nuts3": c.nuts3,
            "nuts2": c.nuts2,
            "count": counts.get(c.code, 0),
        }
        for c in counties()
    ]
    total = sum(counts.values())
    in_county = counts.get(county_obj.code, 0) if county_obj else None
    in_region = sum(i["count"] for i in by_county if i["nuts2"] == nuts2) if nuts2 else None
    advice = build_advice(
        single_bid_share=comp["single_bid_share"],
        n_awards=comp["n"],
        competition_scope=comp["scope"],
        suppliers_in_county=in_county,
        county_name=county_obj.name if county_obj else None,
        suppliers_in_region=in_region,
        region_code=nuts2,
    )
    n_companies = session.scalar(select(func.count()).select_from(Company)) or 0
    return {
        "input": {"text": text_input, "cpv": cpv, "county": county},
        "cpv_suggestions": suggestions,
        "division": {"code": division, "label": label_for_prefix(session, division)},
        "cpv_group": group,
        "suppliers": {
            "tau": tau,
            "tau_calibrated": cfg["calibrated"],
            "total": total,
            "in_county": in_county,
            "in_region": in_region,
            "companies_in_register": n_companies,
        },
        "suppliers_by_county": by_county,
        "competition": {**comp, "national": national},
        "advice": [
            {
                "text": a["text"],
                "source_url": a["source_url"],
                "source_label": a["source_label"],
                "rule": a["rule"],
            }
            for a in advice
        ],
        "data": data_dates(session),
        "generated_at": datetime.now(UTC).isoformat(),
    }
