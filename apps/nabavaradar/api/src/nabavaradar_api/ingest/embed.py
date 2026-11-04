"""Embeddings (multilingual-e5-small, 384-d) for NKD labels, CPV labels and notices.

Roles (task): activities are *queries*, notices and CPV labels are *passages*.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import Any

import numpy as np
import structlog
from numpy.typing import NDArray
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from nabavaradar_api.db import Cpv, Nkd, Notice
from nabavaradar_api.settings import NabavaSettings

log = structlog.get_logger(__name__)

NOTICE_DESCRIPTION_CHARS = 1500  # task: title + description (first 1,500 chars) + CPV labels
MAX_CPV_LABELS = 5
CHUNK = 512

Encoder = Callable[[Sequence[str]], NDArray[np.float32]]


def _encoders() -> tuple[Encoder, Encoder]:
    from opendata_core import semantic

    return semantic.encode_queries, semantic.encode_passages


def notice_text(
    title: str | None, description: str | None, cpv_codes: list[str], cpv_labels: dict[str, str]
) -> str:
    """Notice text: title + description (first 1,500 chars) + the Croatian CPV labels."""
    parts = [title or "", (description or "")[:NOTICE_DESCRIPTION_CHARS]]
    labels: list[str] = []
    for code in cpv_codes:
        label = cpv_labels.get(code)
        if label and label not in labels:
            labels.append(label)
        if len(labels) >= MAX_CPV_LABELS:
            break
    parts.append("; ".join(labels))
    return "\n".join(p.strip() for p in parts if p and p.strip())


def cpv_label_map(session: Session) -> dict[str, str]:
    """Croatian CPV label per 8-digit code (English when no Croatian label exists)."""
    return {
        c: (hr or en) for c, hr, en in session.execute(select(Cpv.code, Cpv.label_hr, Cpv.label_en))
    }


def embed_nkd(session: Session, encode_queries: Encoder | None = None) -> int:
    """Embed NKD labels (as queries); returns the number embedded."""
    enc = encode_queries or _encoders()[0]
    rows = session.execute(
        select(Nkd.code, Nkd.version, Nkd.label_hr).where(Nkd.embedding.is_(None))
    ).all()
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i : i + CHUNK]
        vecs = enc([r.label_hr for r in chunk])
        session.execute(
            update(Nkd),
            [
                {"code": r.code, "version": r.version, "embedding": v}
                for r, v in zip(chunk, vecs, strict=True)
            ],
        )
        session.commit()
    log.info("nkd_embedded", rows=len(rows))
    return len(rows)


def embed_cpv(session: Session, encode_passages: Encoder | None = None) -> int:
    """Embed CPV labels (Croatian, else English) as passages."""
    enc = encode_passages or _encoders()[1]
    rows = session.execute(
        select(Cpv.code, Cpv.label_hr, Cpv.label_en).where(Cpv.embedding.is_(None))
    ).all()
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i : i + CHUNK]
        vecs = enc([r.label_hr or r.label_en for r in chunk])
        session.execute(
            update(Cpv),
            [{"code": r.code, "embedding": v} for r, v in zip(chunk, vecs, strict=True)],
        )
        session.commit()
    log.info("cpv_embedded", rows=len(rows))
    return len(rows)


def embed_notices(
    session: Session, encode_passages: Encoder | None = None, *, limit: int | None = None
) -> int:
    """Embed notices that have no embedding yet (passages); returns the number embedded."""
    enc = encode_passages or _encoders()[1]
    labels = cpv_label_map(session)
    query = (
        select(Notice.pub_no, Notice.title, Notice.description, Notice.cpv_codes)
        .where(Notice.embedding.is_(None))
        .order_by(Notice.pub_date.desc(), Notice.pub_no)
    )
    if limit:
        query = query.limit(limit)
    rows = session.execute(query).all()
    done = 0
    for i in range(0, len(rows), CHUNK):
        chunk = rows[i : i + CHUNK]
        texts = [
            notice_text(r.title, r.description, list(r.cpv_codes or []), labels) or r.pub_no
            for r in chunk
        ]
        vecs = enc(texts)
        session.execute(
            update(Notice),
            [{"pub_no": r.pub_no, "embedding": v} for r, v in zip(chunk, vecs, strict=True)],
        )
        session.commit()
        done += len(chunk)
        log.info("notices_embedded", done=done, total=len(rows))
    return done


def embed_all(session: Session, settings: NabavaSettings) -> dict[str, Any]:
    """Embed NKD, CPV and notices (in that order)."""
    return {
        "nkd": embed_nkd(session),
        "cpv": embed_cpv(session),
        "notices": embed_notices(session),
    }
