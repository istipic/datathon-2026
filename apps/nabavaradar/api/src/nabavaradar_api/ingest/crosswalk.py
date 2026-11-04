"""NKD -> CPV crosswalk and the fit calibration (percentiles of activity-notice cosines).

Crosswalk (task): for every NKD entry and every CPV division (2 digits) and group (3 digits),
similarity = cosine(NKD label embedding, mean embedding of the CPV label and up to 200 notice
texts with that CPV prefix); the top-10 per NKD entry and level are kept.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

import numpy as np
import structlog
from numpy.typing import NDArray
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from nabavaradar_api.db import Calibration, CompanyActivity, Cpv, Crosswalk, Nkd, Notice
from nabavaradar_api.settings import NabavaSettings

log = structlog.get_logger(__name__)

TOP_K = 10
NOTICES_PER_PREFIX = 200
CALIBRATION_KEY = "activity_notice_cosine"


def _normalise(v: NDArray[np.float32]) -> NDArray[np.float32]:
    n = np.linalg.norm(v)
    return v if n == 0 else (v / n).astype(np.float32)


def prefix_vectors(
    cpv: dict[str, NDArray[np.float32]],
    notices: list[tuple[str, NDArray[np.float32]]],
    prefixes: list[str],
) -> dict[str, NDArray[np.float32]]:
    """Mean embedding per CPV prefix of (its own label) + up to 200 notices that start with it.

    ``cpv`` maps 8-digit codes to label embeddings; ``notices`` is ``(cpv_main, embedding)`` ordered
    newest first. The own label is the code ``<prefix>000000`` (padded), or - when the prefix has no
    code of its own - the mean of up to 20 labels below it.
    """
    out: dict[str, NDArray[np.float32]] = {}
    for p in prefixes:
        own = cpv.get(p.ljust(8, "0"))
        if own is None:
            below = [v for c, v in cpv.items() if c.startswith(p)][:20]
            own = np.mean(below, axis=0) if below else None
        vecs = [own] if own is not None else []
        count = 0
        for main, emb in notices:
            if main.startswith(p):
                vecs.append(emb)
                count += 1
                if count >= NOTICES_PER_PREFIX:
                    break
        if vecs:
            out[p] = _normalise(np.mean(vecs, axis=0))
    return out


def top_k_rows(
    nkd_keys: list[tuple[str, str]],
    nkd_matrix: NDArray[np.float32],
    prefixes: dict[str, NDArray[np.float32]],
    level: str,
    k: int = TOP_K,
) -> list[dict[str, Any]]:
    """Top-``k`` prefixes per NKD entry by cosine similarity (vectors are L2-normalised)."""
    names = list(prefixes)
    if not names:
        return []
    sims = nkd_matrix @ np.stack([prefixes[n] for n in names]).T
    rows: list[dict[str, Any]] = []
    for i, (code, version) in enumerate(nkd_keys):
        order = np.argsort(-sims[i])[:k]
        for rank, j in enumerate(order, start=1):
            rows.append(
                {
                    "nkd_code": code,
                    "nkd_version": version,
                    "cpv_level": level,
                    "rank": rank,
                    "cpv_prefix": names[j],
                    "similarity": round(float(sims[i, j]), 5),
                }
            )
    return rows


def load_prefix_space(
    session: Session,
) -> tuple[list[tuple[str, str]], NDArray[np.float32], dict[str, dict[str, NDArray[np.float32]]]]:
    """NKD keys, their embedding matrix and the CPV prefix vectors per level (division/group)."""
    nkd = session.execute(
        select(Nkd.code, Nkd.version, Nkd.embedding).where(Nkd.embedding.is_not(None))
    ).all()
    if not nkd:
        raise RuntimeError("no NKD embeddings: run `ingest embed` first")
    keys = [(r.code, r.version) for r in nkd]
    matrix = np.stack([np.asarray(r.embedding, dtype=np.float32) for r in nkd])
    cpv_rows = session.execute(
        select(Cpv.code, Cpv.embedding).where(Cpv.embedding.is_not(None))
    ).all()
    cpv = {r.code: np.asarray(r.embedding, dtype=np.float32) for r in cpv_rows}
    notices = [
        (r.cpv_main, np.asarray(r.embedding, dtype=np.float32))
        for r in session.execute(
            select(Notice.cpv_main, Notice.embedding)
            .where(Notice.embedding.is_not(None), Notice.cpv_main.is_not(None))
            .order_by(Notice.pub_date.desc())
        )
    ]
    levels = {
        "division": prefix_vectors(cpv, notices, sorted({c[:2] for c in cpv})),
        "group": prefix_vectors(cpv, notices, sorted({c[:3] for c in cpv})),
    }
    log.info("prefix_space", nkd=len(keys), cpv=len(cpv), notices_used=len(notices))
    return keys, matrix, levels


def division_similarity(
    session: Session,
) -> tuple[list[tuple[str, str]], list[str], NDArray[np.float32]]:
    """Full NKD x CPV-division cosine matrix (not truncated to the top 10)."""
    keys, matrix, levels = load_prefix_space(session)
    names = list(levels["division"])
    return keys, names, matrix @ np.stack([levels["division"][n] for n in names]).T


def compute_crosswalk(session: Session) -> dict[str, int]:
    """Recompute the whole crosswalk table."""
    keys, matrix, levels = load_prefix_space(session)
    rows: list[dict[str, Any]] = []
    for level, vectors in levels.items():
        rows += top_k_rows(keys, matrix, vectors, level)
    session.execute(delete(Crosswalk))
    for i in range(0, len(rows), 5000):
        session.execute(insert(Crosswalk).values(rows[i : i + 5000]))
    session.commit()
    log.info("crosswalk_computed", nkd=len(keys), rows=len(rows))
    return {"nkd": len(keys), "rows": len(rows)}


def percentiles_of(
    matrix: NDArray[np.float32], lo: float = 5, hi: float = 95
) -> tuple[float, float]:
    """5th and 95th percentile of all values of a similarity matrix."""
    values = matrix.ravel()
    return float(np.percentile(values, lo)), float(np.percentile(values, hi))


def compute_calibration(
    session: Session, settings: NabavaSettings, *, now: datetime | None = None
) -> dict[str, Any]:
    """Store the 5th/95th percentile of all cosines between company activities and open-window
    competition notices (used to rescale S to 0-1)."""
    now = now or datetime.now(UTC)
    since = (now - timedelta(days=settings.competition_days)).date()
    acts = session.execute(
        select(Nkd.code, Nkd.version, Nkd.embedding)
        .join(
            CompanyActivity,
            (CompanyActivity.nkd_code == Nkd.code) & (CompanyActivity.nkd_version == Nkd.version),
        )
        .where(Nkd.embedding.is_not(None))
        .distinct()
    ).all()
    notices = session.execute(
        select(Notice.embedding).where(
            Notice.type == "competition", Notice.embedding.is_not(None), Notice.pub_date >= since
        )
    ).all()
    if not acts or not notices:
        raise RuntimeError("calibration needs company activities and embedded competition notices")
    a = np.stack([np.asarray(r.embedding, dtype=np.float32) for r in acts])
    n = np.stack([np.asarray(r.embedding, dtype=np.float32) for r in notices])
    p5, p95 = percentiles_of(a @ n.T)
    value = {
        "p5": round(p5, 5),
        "p95": round(p95, 5),
        "activities": len(acts),
        "notices": len(notices),
        "window_start": since.isoformat(),
        "computed_at": now.isoformat(),
    }
    stmt = insert(Calibration).values(key=CALIBRATION_KEY, value=value)
    session.execute(
        stmt.on_conflict_do_update(index_elements=[Calibration.key], set_={"value": value})
    )
    session.commit()
    log.info("calibration_stored", **value)
    return value
