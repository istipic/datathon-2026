"""Ranking of open tenders for a company, built on in-memory embeddings of the open notices."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import select
from sqlalchemy.orm import Session

from nabavaradar_api.counties import by_code, by_nuts3, nuts2_of
from nabavaradar_api.db import (
    Calibration,
    CompanyActivity,
    CompetitionStat,
    Cpv,
    Crosswalk,
    Nkd,
    Notice,
)
from nabavaradar_api.fit import (
    Components,
    crosswalk_component,
    days_to_deadline,
    geography_component,
    rank_divisions,
    rescale_similarity,
    time_component,
)
from nabavaradar_api.ingest.crosswalk import CALIBRATION_KEY
from nabavaradar_api.ingest.stats import NATIONAL, competition_flag

MAX_ACTIVITIES = 10  # task: max 10 activities, main first
INDEX_TTL_S = 300.0
DEFAULT_PERCENTILES = (0.0, 1.0)


@dataclass
class Activity:
    """A company activity (NKD entry) or the user's free-text description."""

    label: str
    vec: NDArray[np.float32]
    code: str | None = None
    version: str | None = None
    is_main: bool = False


@dataclass
class OpenIndex:
    """Open competition notices and the statistics, loaded once and refreshed every few minutes."""

    loaded_at: float
    emb: NDArray[np.float32]
    rows: list[dict[str, Any]]
    stats: dict[tuple[str, str], dict[str, Any]]
    p5: float
    p95: float
    division_labels: dict[str, str]
    division_vecs: dict[str, NDArray[np.float32]] = field(default_factory=dict)


def load_activities(session: Session, oib: str) -> list[Activity]:
    """Company activities with embeddings: max 10, main first, newest NKD version first."""
    rows = session.execute(
        select(CompanyActivity.nkd_code, CompanyActivity.nkd_version, CompanyActivity.is_main, Nkd.label_hr, Nkd.embedding)
        .join(Nkd, (Nkd.code == CompanyActivity.nkd_code) & (Nkd.version == CompanyActivity.nkd_version))
        .where(CompanyActivity.oib == oib, Nkd.embedding.is_not(None))
        .order_by(CompanyActivity.is_main.desc(), CompanyActivity.nkd_version.desc(), CompanyActivity.nkd_code)
        .limit(MAX_ACTIVITIES)
    ).all()
    return [
        Activity(r.label_hr, np.asarray(r.embedding, dtype=np.float32), r.nkd_code, r.nkd_version, bool(r.is_main))
        for r in rows
    ]


def load_index(session: Session) -> OpenIndex:
    """Read open competition notices (deadline in the future or unknown), stats and calibration."""
    now = datetime.now(UTC)
    notices = session.execute(
        select(
            Notice.pub_no, Notice.title, Notice.buyer_name, Notice.buyer_nuts, Notice.place_nuts,
            Notice.deadline, Notice.value_eur, Notice.currency, Notice.cpv_main, Notice.url_html,
            Notice.pub_date, Notice.n_lots, Notice.embedding, Notice.retrieved_at,
        ).where(
            Notice.type == "competition",
            Notice.embedding.is_not(None),
            (Notice.deadline.is_(None)) | (Notice.deadline > now),
        )
    ).all()
    rows = [
        {
            "pub_no": n.pub_no, "title": n.title, "buyer": n.buyer_name,
            "nuts3": n.buyer_nuts or n.place_nuts, "deadline": n.deadline,
            "value_eur": float(n.value_eur) if n.value_eur is not None else None,
            "currency": n.currency, "cpv_main": n.cpv_main, "url_html": n.url_html,
            "pub_date": n.pub_date, "n_lots": n.n_lots, "retrieved_at": n.retrieved_at,
        }
        for n in notices
    ]
    emb = (
        np.stack([np.asarray(n.embedding, dtype=np.float32) for n in notices])
        if notices
        else np.zeros((0, 384), dtype=np.float32)
    )
    stats = {
        (s.cpv_group, s.nuts2): {
            "n": s.n_awards,
            "median_submissions": float(s.median_submissions) if s.median_submissions is not None else None,
            "single_bid_share": float(s.single_bid_share) if s.single_bid_share is not None else None,
        }
        for s in session.scalars(select(CompetitionStat))
    }
    cal = session.get(Calibration, CALIBRATION_KEY)
    p5, p95 = (cal.value["p5"], cal.value["p95"]) if cal else DEFAULT_PERCENTILES
    labels = {
        c[:2]: (hr or en)
        for c, hr, en in session.execute(select(Cpv.code, Cpv.label_hr, Cpv.label_en).where(Cpv.code.like("__000000")))
    }
    return OpenIndex(time.monotonic(), emb, rows, stats, float(p5), float(p95), labels)


def competition_info(
    index: OpenIndex, cpv_main: str | None, buyer_nuts: str | None
) -> dict[str, Any]:
    """Competition history for a CPV group: the buyer's NUTS2 when available, else national."""
    empty = {"median_submissions": None, "single_bid_share": None, "n": 0, "flag": False, "scope": None}
    if not cpv_main:
        return empty
    group = cpv_main[:3]
    nuts2 = nuts2_of(buyer_nuts)
    for scope in (nuts2, NATIONAL):
        stat = index.stats.get((group, scope)) if scope else None
        if stat:
            return {
                **{k: stat[k] for k in ("median_submissions", "single_bid_share", "n")},
                "flag": competition_flag(stat["n"], stat["single_bid_share"]),
                "scope": scope,
            }
    return empty


class MatchEngine:
    """Holds the open-notice index; ``match`` is pure numpy once the index is loaded."""

    def __init__(self, ttl_s: float = INDEX_TTL_S) -> None:
        self._ttl = ttl_s
        self._index: OpenIndex | None = None
        self._lock = threading.Lock()

    def index(self, session: Session, *, force: bool = False) -> OpenIndex:
        """The cached index, reloaded when older than the TTL."""
        with self._lock:
            if force or self._index is None or time.monotonic() - self._index.loaded_at > self._ttl:
                self._index = load_index(session)
            return self._index

    def match(
        self,
        session: Session,
        *,
        activities: list[Activity],
        company_nuts3: str | None,
        ranked_divisions: list[str],
        county: int | None = None,
        deadline_min_days: float = 0.0,
        value_min: float | None = None,
        value_max: float | None = None,
        limit: int = 20,
        now: datetime | None = None,
    ) -> list[dict[str, Any]]:
        """Rank open notices; returns the items of the ``/match`` response."""
        now = now or datetime.now(UTC)
        idx = self.index(session)
        if not activities or not idx.rows:
            return []
        sims = idx.emb @ np.stack([a.vec for a in activities]).T  # (notices, activities)
        best = sims.argmax(axis=1)
        best_cos = sims.max(axis=1)
        county_nuts3 = by_code(county).nuts3 if county and by_code(county) else None
        items: list[dict[str, Any]] = []
        for i, row in enumerate(idx.rows):
            days = days_to_deadline(row["deadline"], now)
            t = time_component(days)
            if t is None or (days is not None and days < deadline_min_days):
                continue
            if county_nuts3 and row["nuts3"] != county_nuts3:
                continue
            value = row["value_eur"]
            if (value_min is not None and (value is None or value < value_min)) or (
                value_max is not None and (value is None or value > value_max)
            ):
                continue
            division = row["cpv_main"][:2] if row["cpv_main"] else None
            comp = Components(
                S=rescale_similarity(float(best_cos[i]), idx.p5, idx.p95),
                C=crosswalk_component(division, ranked_divisions),
                G=geography_component(row["nuts3"], company_nuts3),
                T=t,
            )
            act = activities[int(best[i])]
            county_obj = by_nuts3(row["nuts3"])
            items.append(
                {
                    "pub_no": row["pub_no"],
                    "title": row["title"],
                    "buyer": row["buyer"],
                    "nuts3": row["nuts3"],
                    "county": county_obj.name if county_obj else None,
                    "deadline": row["deadline"].isoformat() if row["deadline"] else None,
                    "days_left": round(days, 1) if days is not None else None,
                    "value_eur": value,
                    "fit": comp.fit(),
                    "components": {"S": round(comp.S, 4), "C": comp.C, "G": comp.G, "T": round(comp.T, 4)},
                    "best_activity": {"label": act.label, "code": act.code, "version": act.version},
                    "cpv_main": row["cpv_main"],
                    "cpv_division": division,
                    "cpv_division_label": idx.division_labels.get(division or ""),
                    "division_rank": ranked_divisions.index(division) + 1 if division in ranked_divisions else None,
                    "competition": competition_info(idx, row["cpv_main"], row["nuts3"]),
                    "url_html": row["url_html"],
                    "pub_date": row["pub_date"].isoformat(),
                }
            )
        items.sort(key=lambda x: (-x["fit"], x["deadline"] or "9999"))
        return items[:limit]


def crosswalk_maps(session: Session, activities: list[Activity]) -> list[dict[str, float]]:
    """Per NKD activity: ``{CPV division: similarity}`` from the stored crosswalk."""
    keys = [(a.code, a.version) for a in activities if a.code]
    if not keys:
        return []
    rows = session.execute(
        select(Crosswalk.nkd_code, Crosswalk.nkd_version, Crosswalk.cpv_prefix, Crosswalk.similarity).where(
            Crosswalk.cpv_level == "division",
            Crosswalk.nkd_code.in_([k[0] for k in keys]),
        )
    ).all()
    wanted = set(keys)
    per: dict[tuple[str, str], dict[str, float]] = {}
    for r in rows:
        if (r.nkd_code, r.nkd_version) in wanted:
            per.setdefault((r.nkd_code, r.nkd_version), {})[r.cpv_prefix] = float(r.similarity)
    return list(per.values())


def company_division_ranking(session: Session, activities: list[Activity]) -> list[str]:
    """Company's CPV divisions by max crosswalk similarity over its (NKD) activities."""
    return rank_divisions(crosswalk_maps(session, activities))
