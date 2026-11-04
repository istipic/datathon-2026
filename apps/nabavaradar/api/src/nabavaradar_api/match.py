"""Ranking of open tenders for a company, built on in-memory embeddings of the open notices."""

from __future__ import annotations

import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
from numpy.typing import NDArray
from sqlalchemy import literal_column, select
from sqlalchemy.orm import Session

from nabavaradar_api.counties import by_code, by_nuts3, nuts2_of
from nabavaradar_api.db import (
    Calibration,
    Company,
    CompanyActivity,
    CompetitionStat,
    Cpv,
    Crosswalk,
    Nkd,
    Notice,
)
from nabavaradar_api.fit import (
    Components,
    FitConfig,
    crosswalk_component,
    days_to_deadline,
    geography_component,
    group_component,
    load_fit_config,
    rank_divisions,
    time_component,
)
from nabavaradar_api.ingest.crosswalk import CALIBRATION_KEY
from nabavaradar_api.ingest.stats import NATIONAL, competition_flag

MAX_ACTIVITIES = 10  # task: max 10 activities, main first
INDEX_TTL_S = 300.0
UNKNOWN_DEADLINE_DAYS = 120
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
        select(
            CompanyActivity.nkd_code,
            CompanyActivity.nkd_version,
            CompanyActivity.is_main,
            Nkd.label_hr,
            Nkd.embedding,
        )
        .join(
            Nkd,
            (Nkd.code == CompanyActivity.nkd_code) & (Nkd.version == CompanyActivity.nkd_version),
        )
        .where(CompanyActivity.oib == oib, Nkd.embedding.is_not(None))
        .order_by(
            CompanyActivity.is_main.desc(),
            CompanyActivity.nkd_version.desc(),
            CompanyActivity.nkd_code,
        )
        .limit(MAX_ACTIVITIES)
    ).all()
    return [
        Activity(
            r.label_hr,
            np.asarray(r.embedding, dtype=np.float32),
            r.nkd_code,
            r.nkd_version,
            bool(r.is_main),
        )
        for r in rows
    ]


def load_index(session: Session, now: datetime | None = None) -> OpenIndex:
    """Read open competition notices (deadline in the future or unknown), stats and calibration."""
    now = now or datetime.now(UTC)
    cfg = load_fit_config()
    notices = session.execute(
        select(
            Notice.pub_no,
            Notice.title,
            Notice.buyer_name,
            Notice.buyer_nuts,
            Notice.place_nuts,
            Notice.deadline,
            Notice.value_eur,
            Notice.currency,
            Notice.cpv_main,
            Notice.url_html,
            Notice.pub_date,
            Notice.n_lots,
            Notice.notice_type,
            Notice.procedure_id,
            literal_column("(notice.raw ? 'deadline-receipt-tender-date-lot')").label(
                "has_tender_deadline"
            ),
            Notice.embedding,
            Notice.retrieved_at,
        ).where(
            Notice.type == "competition",
            Notice.embedding.is_not(None),
            Notice.notice_type.not_in(cfg.excluded_notice_types)
            if cfg.excluded_notice_types
            else literal_column("true"),
            # a notice without any deadline is kept only while it is recent: old ones would be shown as
            # open forever
            (Notice.deadline > now)
            | (
                Notice.deadline.is_(None)
                & (Notice.pub_date >= (now - timedelta(days=UNKNOWN_DEADLINE_DAYS)).date())
            ),
        )
    ).all()
    rows = [
        {
            "pub_no": n.pub_no,
            "title": n.title,
            "buyer": n.buyer_name,
            "nuts3": n.buyer_nuts or n.place_nuts,
            "deadline": n.deadline,
            "value_eur": float(n.value_eur) if n.value_eur is not None else None,
            "currency": n.currency,
            "cpv_main": n.cpv_main,
            "url_html": n.url_html,
            "pub_date": n.pub_date,
            "deadline_kind": ("tender" if n.has_tender_deadline else "request")
            if n.deadline
            else None,
            "n_lots": n.n_lots,
            "notice_type": n.notice_type,
            "procedure_id": n.procedure_id,
            "retrieved_at": n.retrieved_at,
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
            "median_submissions": float(s.median_submissions)
            if s.median_submissions is not None
            else None,
            "single_bid_share": float(s.single_bid_share)
            if s.single_bid_share is not None
            else None,
        }
        for s in session.scalars(select(CompetitionStat))
    }
    cal = session.get(Calibration, CALIBRATION_KEY)
    p5, p95 = (cal.value["p5"], cal.value["p95"]) if cal else DEFAULT_PERCENTILES
    labels = {
        c[:2]: (hr or en)
        for c, hr, en in session.execute(
            select(Cpv.code, Cpv.label_hr, Cpv.label_en).where(Cpv.code.like("__000000"))
        )
    }
    return OpenIndex(time.monotonic(), emb, rows, stats, float(p5), float(p95), labels)


def competition_info(
    index: OpenIndex, cpv_main: str | None, buyer_nuts: str | None
) -> dict[str, Any]:
    """Competition history for a CPV group: the buyer's NUTS2 when available, else national."""
    empty = {
        "median_submissions": None,
        "single_bid_share": None,
        "n": 0,
        "flag": False,
        "scope": None,
    }
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


_LOT_WORDS = re.compile(r"\b(grupa|skupina|lot|dio|dijel)\s*\d+\b", re.IGNORECASE)
_NON_WORD = re.compile(r"[^\w]+", re.UNICODE)


def procedure_key(item: dict[str, Any]) -> str:
    """Key of the procedure a notice belongs to: the TED procedure id, else buyer plus base title.

    The same procedure is published several times (corrigenda, repeated publication) and lots of one
    purchase are often split into near-identical titles ("... grupa 1", "... grupa 2")."""
    if item.get("procedure_id"):
        return f"p:{item['procedure_id']}"
    title = _NON_WORD.sub(" ", _LOT_WORDS.sub("", (item.get("title") or "").lower())).strip()
    digits_free = re.sub(r"\d+", "", title)
    return f"t:{(item.get('buyer') or '').lower()}|{digits_free[:90]}"


def collapse_procedures(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """One item per procedure (the best-ranked, newest on ties); the others go to ``group``.

    ``items`` must already be sorted best first; the order of the kept items is preserved."""
    kept: dict[str, dict[str, Any]] = {}
    order: list[str] = []
    for item in items:
        key = procedure_key(item)
        if key not in kept:
            kept[key] = {**item, "group": {"size": 1, "others": []}}
            order.append(key)
            continue
        head = kept[key]
        head["group"]["size"] += 1
        head["group"]["others"].append(
            {
                "pub_no": item["pub_no"],
                "pub_date": item["pub_date"],
                "title": item["title"],
                "fit": item["fit"],
                "deadline": item["deadline"],
                "url_html": item["url_html"],
            }
        )
        if item["fit"] == head["fit"] and item["pub_date"] > head["pub_date"]:
            others = head["group"]["others"]
            others.pop()  # the newer publication of equal fit becomes the head instead
            others.append(
                {k: head[k] for k in ("pub_no", "pub_date", "title", "fit", "deadline", "url_html")}
            )
            group = head["group"]
            kept[key] = {**item, "group": group}
    return [kept[k] for k in order]


class MatchEngine:
    """Holds the open-notice index; ``match`` is pure numpy once the index is loaded."""

    def __init__(self, ttl_s: float = INDEX_TTL_S) -> None:
        self._ttl = ttl_s
        self._index: OpenIndex | None = None
        self._lock = threading.Lock()

    def index(
        self, session: Session, *, force: bool = False, now: datetime | None = None
    ) -> OpenIndex:
        """The cached index, reloaded when older than the TTL."""
        with self._lock:
            if force or self._index is None or time.monotonic() - self._index.loaded_at > self._ttl:
                self._index = load_index(session, now)
            return self._index

    def match(
        self,
        session: Session,
        *,
        activities: list[Activity],
        company_nuts3: str | None,
        ranked_divisions: list[str],
        ranked_groups: list[str] | None = None,
        county: int | None = None,
        deadline_min_days: float = 0.0,
        value_min: float | None = None,
        value_max: float | None = None,
        counties_nuts3: set[str] | None = None,
        cpv_divisions: set[str] | None = None,
        hidden: set[str] | None = None,
        dislike_groups: set[str] | None = None,
        group_lots: bool = False,
        limit: int = 20,
        now: datetime | None = None,
        cfg: FitConfig | None = None,
    ) -> list[dict[str, Any]]:
        """Rank open notices; returns the items of the ``/match`` response.

        ``hidden`` notices (and every other notice of the same procedure) are left out, notices of the
        ``dislike_groups`` (CPV groups, 3 digits) lose ``cfg.dislike_penalty``. With ``group_lots`` the
        notices of one procedure are collapsed into the best one (``group`` lists the others).
        """
        now = now or datetime.now(UTC)
        cfg = cfg or load_fit_config()
        idx = self.index(session, now=now)
        if not activities or not idx.rows:
            return []
        sims = idx.emb @ np.stack([a.vec for a in activities]).T  # (notices, activities)
        main_flags = [a.is_main for a in activities]
        if not any(main_flags):
            main_flags[0] = True  # no flagged main activity: the first one counts as the main one
        discount = np.where(main_flags, 1.0, cfg.secondary_activity_discount)
        scaled = np.clip((sims - idx.p5) / max(idx.p95 - idx.p5, 1e-9), 0.0, 1.0) * discount
        best = scaled.argmax(axis=1)
        s_all = scaled.max(axis=1)
        best_cos = sims[np.arange(len(sims)), best]
        county_nuts3 = by_code(county).nuts3 if county and by_code(county) else None
        hidden = hidden or set()
        hidden_procedures = {r["procedure_id"] for r in idx.rows if r["pub_no"] in hidden} - {None}
        dislike_groups = dislike_groups or set()
        top_groups = (ranked_groups or [])[: cfg.c_group_top]
        items: list[dict[str, Any]] = []
        for i, row in enumerate(idx.rows):
            days = days_to_deadline(row["deadline"], now)
            t = time_component(days)
            if t is None or (days is not None and days < deadline_min_days):
                continue
            if row["pub_no"] in hidden or row["procedure_id"] in hidden_procedures:
                continue
            if county_nuts3 and row["nuts3"] != county_nuts3:
                continue
            if counties_nuts3 and row["nuts3"] not in counties_nuts3:
                continue
            value = row["value_eur"]
            if (value_min is not None and (value is None or value < value_min)) or (
                value_max is not None and (value is None or value > value_max)
            ):
                continue
            division = row["cpv_main"][:2] if row["cpv_main"] else None
            if cpv_divisions and division not in cpv_divisions:
                continue
            group = row["cpv_main"][:3] if row["cpv_main"] else None
            c_div = crosswalk_component(division, ranked_divisions)
            c_bonus = group_component(group, top_groups, cfg)
            comp = Components(
                S=float(s_all[i]),
                C=min(1.0, c_div + c_bonus),
                G=geography_component(row["nuts3"], company_nuts3),
                T=t,
            )
            fit = comp.fit(cfg.weights)
            if group in dislike_groups:
                fit = round(max(0.0, fit - cfg.dislike_penalty), 4)
            act = activities[int(best[i])]
            county_obj = by_nuts3(row["nuts3"])
            items.append(
                {
                    "pub_no": row["pub_no"],
                    "procedure_id": row["procedure_id"],
                    "notice_type": row["notice_type"],
                    "title": row["title"],
                    "buyer": row["buyer"],
                    "nuts3": row["nuts3"],
                    "county": county_obj.name if county_obj else None,
                    "deadline": row["deadline"].isoformat() if row["deadline"] else None,
                    "deadline_kind": row["deadline_kind"],
                    "days_left": round(days, 1) if days is not None else None,
                    "value_eur": value,
                    "fit": fit,
                    "similarity": round(float(best_cos[i]), 4),
                    "components": {
                        "S": round(comp.S, 4),
                        "C": round(comp.C, 4),
                        "G": comp.G,
                        "T": round(comp.T, 4),
                    },
                    "signals": {
                        "main_activity": act.is_main or act.code is None,
                        "cpv_group_match": c_bonus > 0,
                        "disliked_group": group in dislike_groups,
                    },
                    "best_activity": {"label": act.label, "code": act.code, "version": act.version},
                    "cpv_main": row["cpv_main"],
                    "cpv_division": division,
                    "cpv_group": group,
                    "cpv_division_label": idx.division_labels.get(division or ""),
                    "division_rank": ranked_divisions.index(division) + 1
                    if division in ranked_divisions
                    else None,
                    "competition": competition_info(idx, row["cpv_main"], row["nuts3"]),
                    "url_html": row["url_html"],
                    "pub_date": row["pub_date"].isoformat(),
                }
            )
        # S saturates at the 95th percentile, so ties are common at the top: break them by the raw cosine
        items.sort(key=lambda x: (-x["fit"], -x["similarity"], x["deadline"] or "9999"))
        if group_lots:
            items = collapse_procedures(items)
        return items[:limit]


def crosswalk_maps(
    session: Session, activities: list[Activity], level: str = "division"
) -> list[dict[str, float]]:
    """Per NKD activity: ``{CPV prefix: similarity}`` from the stored crosswalk (division or group)."""
    keys = [(a.code, a.version) for a in activities if a.code]
    if not keys:
        return []
    rows = session.execute(
        select(
            Crosswalk.nkd_code, Crosswalk.nkd_version, Crosswalk.cpv_prefix, Crosswalk.similarity
        ).where(
            Crosswalk.cpv_level == level,
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


class CompanyNotLoaded(LookupError):
    """The OIB is not in the ``company`` table."""


@dataclass
class Profile:
    """What the matcher needs to know about the user: activities, county and CPV rankings."""

    activities: list[Activity]
    nuts3: str | None
    ranked_divisions: list[str]
    ranked_groups: list[str]


def build_profile_full(
    session: Session, *, oib: str | None, q: str | None, encode: Callable[[list[str]], Any]
) -> Profile:
    """Activities (company NKD activities plus the optional free-text description), the company's
    NUTS3 and the ranked CPV divisions and groups. Used by ``/match`` and the e-mail alerts alike."""
    from nabavaradar_api.sounding import cpv_index

    activities: list[Activity] = []
    nuts3: str | None = None
    if oib is not None:
        company = session.get(Company, oib)
        if company is None:
            raise CompanyNotLoaded(oib)
        nuts3 = company.nuts3
        activities = load_activities(session, oib)
    extra_div: list[dict[str, float]] = []
    extra_grp: list[dict[str, float]] = []
    if q and q.strip():
        vec = np.asarray(encode([q.strip()])[0], dtype=np.float32)
        # the user's own description is what they say they do: it counts as a main activity
        activities = [
            Activity(label=q.strip()[:120], vec=vec, code=None, is_main=True),
            *activities,
        ]
        idx = cpv_index(session)
        sims = idx.emb @ vec
        extra_div.append(
            {c[:2]: float(x) for c, x in zip(idx.codes, sims, strict=True) if c.endswith("000000")}
        )
        extra_grp.append(
            {
                c[:3]: float(x)
                for c, x in zip(idx.codes, sims, strict=True)
                if c.endswith("00000") and not c.endswith("000000")
            }
        )
    return Profile(
        activities,
        nuts3,
        rank_divisions([*extra_div, *crosswalk_maps(session, activities)]),
        rank_divisions([*extra_grp, *crosswalk_maps(session, activities, "group")]),
    )


def build_profile(
    session: Session, *, oib: str | None, q: str | None, encode: Callable[[list[str]], Any]
) -> tuple[list[Activity], str | None, list[str]]:
    """``build_profile_full`` as the ``(activities, nuts3, ranked divisions)`` triple."""
    p = build_profile_full(session, oib=oib, q=q, encode=encode)
    return p.activities, p.nuts3, p.ranked_divisions
