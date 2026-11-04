"""``nabavaradar eval``: recall of real winners on historical awards, baseline, and tau selection.

Protocol (task): take result notices whose winner is a valid OIB found in ``company``; for each
winner, rank all competition notices of the month in which the winner's actual tender was published
and check whether it lands in the top 10 / top 20. The link between a result notice and its
competition notice is the TED ``procedure-identifier``. Where no link exists the result notice
itself is ranked among that month's result notices (reported as such).

Method: the fit score (S, C, G, T) with each candidate evaluated *at its own publication date*.
Baseline: PostgreSQL full-text search (``simple`` configuration) with the winner's activity labels.
"""

from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any

import numpy as np
import structlog
from numpy.typing import NDArray
from sqlalchemy import select, text
from sqlalchemy.orm import Session

from nabavaradar_api.constants import WEIGHTS
from nabavaradar_api.counties import counties, nuts2_of
from nabavaradar_api.db import Calibration, Company, CompanyActivity, Crosswalk, Nkd, Notice
from nabavaradar_api.fit import (
    G_OTHER,
    G_SAME_NUTS2,
    G_SAME_NUTS3,
    G_UNKNOWN,
    T_FULL_DAYS,
    T_ZERO_DAYS,
    rank_divisions,
)
from nabavaradar_api.ingest.crosswalk import CALIBRATION_KEY, division_similarity
from nabavaradar_api.match import MAX_ACTIVITIES
from nabavaradar_api.oib import is_valid_oib

log = structlog.get_logger(__name__)

KS = (10, 20)
MIN_LINKED_FOR_PRIMARY = 100  # below this the result-notice fallback is used
EVAL_KEY = "eval_latest"
TOKEN_RE = re.compile(r"[^\W\d_]{4,}", re.UNICODE)
MAX_FTS_TOKENS = 40


@dataclass
class Winner:
    """One winner/target pair to rank."""

    oib: str
    target: str  # pub_no of the competition notice (or of the result notice in fallback mode)
    month: str  # YYYY-MM of the target


def month_of(d: date) -> str:
    """``YYYY-MM`` of a date."""
    return f"{d.year:04d}-{d.month:02d}"


def fts_query(labels: list[str]) -> str | None:
    """OR-query of the distinct word tokens (>= 4 letters) of the activity labels."""
    seen: dict[str, None] = {}
    for label in labels:
        for token in TOKEN_RE.findall(label.lower()):
            seen.setdefault(token, None)
    tokens = list(seen)[:MAX_FTS_TOKENS]
    return " | ".join(tokens) if tokens else None


def recall_at(ranks: list[int | None], k: int) -> float | None:
    """Share of ranked winners whose target is within the top ``k`` (``None`` rank = a miss)."""
    return sum(1 for r in ranks if r is not None and r <= k) / len(ranks) if ranks else None


# ---------------------------------------------------------------------------- candidate tables


@dataclass
class MonthIndex:
    """Candidates of one month as arrays."""

    pub_nos: list[str]
    emb: NDArray[np.float32]
    division_idx: NDArray[np.int64]  # CPV division as int, -1 unknown
    nuts_idx: NDArray[np.int64]  # index into the county list, -1 unknown
    t: NDArray[np.float64]  # time component at the candidate's own publication date
    valid: NDArray[np.bool_]
    position: dict[str, int]


def _t_at_publication(deadline: datetime | None, pub: date) -> float | None:
    """T evaluated on the publication date; ``None`` when the deadline precedes publication."""
    if deadline is None:
        return 0.5
    days = (deadline - datetime(pub.year, pub.month, pub.day, tzinfo=UTC)).total_seconds() / 86400.0
    if days < 0:
        return None
    if days >= T_FULL_DAYS:
        return 1.0
    return 0.0 if days <= T_ZERO_DAYS else (days - T_ZERO_DAYS) / (T_FULL_DAYS - T_ZERO_DAYS)


def build_month_index(session: Session, kind: str, month: str, nuts_pos: dict[str, int]) -> MonthIndex:
    """Candidates of a month: competition notices (or result notices in fallback mode)."""
    year, mon = int(month[:4]), int(month[5:7])
    start = date(year, mon, 1)
    end = date(year + (mon == 12), 1 if mon == 12 else mon + 1, 1)
    rows = session.execute(
        select(
            Notice.pub_no, Notice.embedding, Notice.cpv_main, Notice.buyer_nuts, Notice.place_nuts,
            Notice.deadline, Notice.pub_date,
        ).where(Notice.type == kind, Notice.pub_date >= start, Notice.pub_date < end, Notice.embedding.is_not(None))
    ).all()
    emb = np.stack([np.asarray(r.embedding, dtype=np.float32) for r in rows]) if rows else np.zeros((0, 384), np.float32)
    division = np.array([int(r.cpv_main[:2]) if r.cpv_main else -1 for r in rows], dtype=np.int64)
    nuts = np.array([nuts_pos.get(r.buyer_nuts or r.place_nuts or "", -1) for r in rows], dtype=np.int64)
    t_values = [_t_at_publication(r.deadline, r.pub_date) if kind == "competition" else 0.5 for r in rows]
    valid = np.array([t is not None for t in t_values], dtype=bool)
    t = np.array([t if t is not None else 0.0 for t in t_values], dtype=np.float64)
    return MonthIndex([r.pub_no for r in rows], emb, division, nuts, t, valid, {r.pub_no: i for i, r in enumerate(rows)})


def g_table(nuts3_codes: list[str]) -> NDArray[np.float64]:
    """Lookup table [company county][candidate county] of the G component (+ last row/col unknown)."""
    n = len(nuts3_codes)
    table = np.full((n + 1, n + 1), G_UNKNOWN)
    for i, a in enumerate(nuts3_codes):
        for j, b in enumerate(nuts3_codes):
            if a == b:
                table[i, j] = G_SAME_NUTS3
            else:
                table[i, j] = G_SAME_NUTS2 if nuts2_of(a) == nuts2_of(b) else G_OTHER
    return table


def c_vector(ranked: list[str]) -> NDArray[np.float64]:
    """C component per CPV division number 0-99 (and index -1 -> last slot) from a ranking."""
    vec = np.zeros(101)
    for pos, division in enumerate(ranked[:10]):
        if division.isdigit():
            vec[int(division)] = 1.0 if pos < 3 else 0.5
    return vec


# ---------------------------------------------------------------------------- main evaluation


def load_winners(session: Session) -> dict[str, Any]:
    """Eligible winners and their targets, with linkage statistics."""
    known = {o for (o,) in session.execute(select(Company.oib))}
    rows = session.execute(
        text(
            """
            SELECT DISTINCT a.winner_national_id AS oib, r.pub_no AS result_no, r.procedure_id,
                   c.pub_no AS competition_no, r.pub_date AS result_date, r.cpv_main AS result_cpv
            FROM award a
            JOIN notice r ON r.pub_no = a.pub_no AND r.type = 'result'
            LEFT JOIN notice c ON c.procedure_id = r.procedure_id AND c.type = 'competition'
            WHERE a.lot_status = 'selec-w' AND a.winner_national_id ~ '^[0-9]{11}$'
            """
        )
    ).all()
    awards_total = len(rows)
    valid = [r for r in rows if is_valid_oib(r.oib)]
    in_company = [r for r in valid if r.oib in known]
    return {
        "rows": in_company,
        "awards_with_winner_id": awards_total,
        "valid_oib": len(valid),
        "in_company": len(in_company),
    }


def load_company_activities(session: Session, oibs: set[str]) -> dict[str, list[tuple[str, str]]]:
    """Per OIB: up to 10 (code, version) pairs, main first, newest NKD version first."""
    out: dict[str, list[tuple[str, str]]] = defaultdict(list)
    rows = session.execute(
        select(CompanyActivity.oib, CompanyActivity.nkd_code, CompanyActivity.nkd_version, CompanyActivity.is_main)
        .where(CompanyActivity.oib.in_(oibs))
        .order_by(CompanyActivity.oib, CompanyActivity.is_main.desc(), CompanyActivity.nkd_version.desc(), CompanyActivity.nkd_code)
    ).all()
    for r in rows:
        if len(out[r.oib]) < MAX_ACTIVITIES:
            out[r.oib].append((r.nkd_code, r.nkd_version))
    return out


def run_evaluation(session: Session, *, now: datetime | None = None) -> dict[str, Any]:
    """Run the whole validation and return the result document (stored by the caller)."""
    now = now or datetime.now(UTC)
    cal = session.get(Calibration, CALIBRATION_KEY)
    if cal is None:
        raise RuntimeError("calibration missing: run `nabavaradar ingest derive` first")
    p5, p95 = float(cal.value["p5"]), float(cal.value["p95"])

    winners = load_winners(session)
    rows = winners["rows"]
    linked = [r for r in rows if r.competition_no]
    mode = "linked" if len({(r.oib, r.competition_no) for r in linked}) >= MIN_LINKED_FOR_PRIMARY else "result_fallback"
    kind = "competition" if mode == "linked" else "result"
    log.info("eval_mode", mode=mode, eligible=len(rows), linked=len(linked))

    pairs: dict[tuple[str, str], Winner] = {}
    for r in rows:
        target = r.competition_no if mode == "linked" else r.result_no
        if not target:
            continue
        date_of = session.get(Notice, target).pub_date  # type: ignore[union-attr]
        pairs.setdefault((r.oib, target), Winner(r.oib, target, month_of(date_of)))
    all_winners = list(pairs.values())

    oibs = {w.oib for w in all_winners}
    activities = load_company_activities(session, oibs)
    nkd_rows = session.execute(select(Nkd.code, Nkd.version, Nkd.label_hr, Nkd.embedding).where(Nkd.embedding.is_not(None))).all()
    nkd_index = {(r.code, r.version): i for i, r in enumerate(nkd_rows)}
    nkd_emb = np.stack([np.asarray(r.embedding, dtype=np.float32) for r in nkd_rows])
    nkd_label = {(r.code, r.version): r.label_hr for r in nkd_rows}
    cw: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)
    for r in session.execute(select(Crosswalk.nkd_code, Crosswalk.nkd_version, Crosswalk.cpv_prefix, Crosswalk.similarity).where(Crosswalk.cpv_level == "division")):
        cw[(r.nkd_code, r.nkd_version)][r.cpv_prefix] = float(r.similarity)
    company_nuts = dict(session.execute(select(Company.oib, Company.nuts3).where(Company.oib.in_(oibs))).all())

    nuts_codes = [c.nuts3 for c in counties()]
    nuts_pos = {n: i for i, n in enumerate(nuts_codes)}
    gtab = g_table(nuts_codes)

    by_month: dict[str, list[Winner]] = defaultdict(list)
    for w in all_winners:
        by_month[w.month].append(w)

    ranks_fit: list[int | None] = []
    ranks_fts: list[int | None] = []
    scored_flags: list[bool] = []
    unscored = 0
    candidate_counts: list[int] = []
    fts_cache: dict[tuple[str, str], list[str]] = {}
    w_s, w_c, w_g, w_t = (WEIGHTS[k] for k in ("S", "C", "G", "T"))
    for month, group in sorted(by_month.items()):
        idx = build_month_index(session, kind, month, nuts_pos)
        if not len(idx.pub_nos):
            continue
        year, mon = int(month[:4]), int(month[5:7])
        m_start = date(year, mon, 1)
        m_end = date(year + (mon == 12), 1 if mon == 12 else mon + 1, 1)
        for w in group:
            if w.target not in idx.position:
                continue
            acts = [k for k in activities.get(w.oib, []) if k in nkd_index]
            if not acts:
                unscored += 1
                scored_flags.append(False)
                ranks_fit.append(None)
                ranks_fts.append(None)
                candidate_counts.append(len(idx.pub_nos))
                continue
            scored_flags.append(True)
            sims = idx.emb @ nkd_emb[[nkd_index[k] for k in acts]].T
            s = np.clip((sims.max(axis=1) - p5) / max(p95 - p5, 1e-9), 0.0, 1.0)
            c = c_vector(rank_divisions([cw[k] for k in acts]))[idx.division_idx]
            home = nuts_pos.get(company_nuts.get(w.oib) or "", -1)
            g = gtab[home][np.where(idx.nuts_idx < 0, len(nuts_codes), idx.nuts_idx)] if home >= 0 else np.full(len(idx.pub_nos), G_UNKNOWN)
            fit = w_s * s + w_c * c + w_g * g + w_t * idx.t
            fit = np.where(idx.valid, fit, -1.0)
            ti = idx.position[w.target]
            ranks_fit.append(int((fit >= fit[ti]).sum()) if idx.valid[ti] else None)
            candidate_counts.append(int(idx.valid.sum()))
            # --- baseline: full-text search over the same month's notices
            query = fts_query([nkd_label[k] for k in acts])
            if not query:
                ranks_fts.append(None)
                continue
            key = (query, month)
            if key not in fts_cache:
                fts_cache[key] = [
                    r.pub_no
                    for r in session.execute(
                        text(
                            """
                            SELECT pub_no FROM notice, to_tsquery('simple', :q) q
                            WHERE type = :kind AND pub_date >= :a AND pub_date < :b
                              AND to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(description,'')) @@ q
                            ORDER BY ts_rank(to_tsvector('simple', coalesce(title,'') || ' ' || coalesce(description,'')), q) DESC, pub_no
                            """
                        ),
                        {"q": query, "kind": kind, "a": m_start, "b": m_end},
                    )
                ]
            order = fts_cache[key]
            ranks_fts.append(order.index(w.target) + 1 if w.target in order else None)

    n = len(ranks_fit)
    result: dict[str, Any] = {
        "computed_at": now.isoformat(),
        "mode": mode,
        "mode_note": (
            "Cilj je stvarna natječajna obavijest pobjednika (veza preko procedure-identifier)."
            if mode == "linked"
            else "Veza rezultat-natječaj nije dostupna: rangira se sama obavijest o rezultatu među obavijestima o rezultatu istog mjeseca."
        ),
        "n": n,
        "n_scored": n - unscored,
        "n_without_activities": unscored,
        "ks": list(KS),
        "fit": {f"recall@{k}": recall_at(ranks_fit, k) for k in KS},
        "fts_baseline": {f"recall@{k}": recall_at(ranks_fts, k) for k in KS},
        "fit_scored_only": {
            f"recall@{k}": recall_at([r for r, ok in zip(ranks_fit, scored_flags, strict=True) if ok], k) for k in KS
        },
        "fts_baseline_scored_only": {
            f"recall@{k}": recall_at([r for r, ok in zip(ranks_fts, scored_flags, strict=True) if ok], k) for k in KS
        },
        "random_baseline": {f"recall@{k}": float(np.mean([min(1.0, k / c) for c in candidate_counts])) if candidate_counts else None for k in KS},
        "mean_candidates_per_target": float(np.mean(candidate_counts)) if candidate_counts else None,
        "median_rank_fit": float(np.median([r for r in ranks_fit if r is not None])) if any(r is not None for r in ranks_fit) else None,
        "months": sorted(by_month),
        "window": {"first_month": min(by_month) if by_month else None, "last_month": max(by_month) if by_month else None},
        "linkage": {
            "award_winner_pairs_with_id": winners["awards_with_winner_id"],
            "valid_oib": winners["valid_oib"],
            "found_in_company": winners["in_company"],
            "linked_to_competition_notice": len({(r.oib, r.competition_no) for r in linked}),
        },
        "calibration": {"p5": p5, "p95": p95},
    }
    result["tau"] = select_tau(session, rows)
    return result


# ---------------------------------------------------------------------------- tau


def select_tau(session: Session, winner_rows: list[Any]) -> dict[str, Any]:
    """Choose tau maximising F1 of winners' activities vs the CPV divisions they won contracts in.

    For every (winner, CPV division) pair the prediction is "capable" when any of the winner's
    activities has crosswalk similarity >= tau to that division; the truth is the set of divisions
    of the awards the winner actually received (result notices' main CPV).
    """
    keys, names, sim = division_similarity(session)
    key_pos = {k: i for i, k in enumerate(keys)}
    div_pos = {d: j for j, d in enumerate(names)}
    truth: dict[str, set[int]] = defaultdict(set)
    for r in winner_rows:
        if r.result_cpv and r.result_cpv[:2] in div_pos:
            truth[r.oib].add(div_pos[r.result_cpv[:2]])
    acts = load_company_activities(session, set(truth))
    oibs = [o for o in truth if any(k in key_pos for k in acts.get(o, []))]
    if not oibs:
        return {"tau": None, "reason": "no winners with activities"}
    capable = np.zeros((len(oibs), len(names)), dtype=np.float32)
    truth_m = np.zeros((len(oibs), len(names)), dtype=bool)
    for i, o in enumerate(oibs):
        rows = [key_pos[k] for k in acts[o] if k in key_pos]
        capable[i] = sim[rows].max(axis=0)
        for j in truth[o]:
            truth_m[i, j] = True
    lo, hi = float(np.percentile(capable, 50)), float(capable.max())
    best: dict[str, Any] = {"f1": -1.0}
    curve = []
    for tau in np.linspace(lo, hi, 201):
        pred = capable >= tau
        tp = int((pred & truth_m).sum())
        fp = int((pred & ~truth_m).sum())
        fn = int((~pred & truth_m).sum())
        f1 = 2 * tp / max(2 * tp + fp + fn, 1)
        if f1 > best["f1"]:
            best = {
                "tau": round(float(tau), 4),
                "f1": round(f1, 4),
                "precision": round(tp / max(tp + fp, 1), 4),
                "recall": round(tp / max(tp + fn, 1), 4),
                "tp": tp, "fp": fp, "fn": fn,
            }
        curve.append((round(float(tau), 4), round(f1, 4)))
    best.update({"winners": len(oibs), "truth_pairs": int(truth_m.sum()), "grid": [lo, hi], "curve_sample": curve[::20]})
    return best


def store_evaluation(session: Session, result: dict[str, Any]) -> None:
    """Persist the latest evaluation for ``GET /validation``."""
    from sqlalchemy.dialects.postgresql import insert

    stmt = insert(Calibration).values(key=EVAL_KEY, value=result)
    session.execute(stmt.on_conflict_do_update(index_elements=[Calibration.key], set_={"value": result}))
    session.commit()
