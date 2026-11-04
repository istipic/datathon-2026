"""HTTP API (``/api/v1``)."""

from __future__ import annotations

import threading
import time
from collections import defaultdict, deque
from collections.abc import Callable
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from nabavaradar_api.company import LookupQueue, company_profile
from nabavaradar_api.counties import counties, valid_county_codes
from nabavaradar_api.db import Award, Calibration, Company, CompetitionStat, Cpv, Notice
from nabavaradar_api.match import CompanyNotLoaded, MatchEngine, build_profile
from nabavaradar_api.oib import is_valid_oib
from nabavaradar_api.settings import NabavaSettings
from nabavaradar_api.sounding import (
    CPV_RE,
    MAX_TEXT,
    competition_for,
    data_dates,
    effective_prefix,
    sound_market,
)
from opendata_core.errors import problem

LOOKUP_WAIT_S = 4.0
MATCH_LIMIT_PER_MIN = 30  # task: /match is limited to 30 requests per minute per IP
NUTS2_CODES = sorted({c.nuts2 for c in counties()})
EVAL_KEY = "eval_latest"


class SlidingLimit:
    """Per-key sliding-window limiter (in-memory, one process)."""

    def __init__(
        self, limit: int, period: float = 60.0, clock: Callable[[], float] = time.monotonic
    ) -> None:
        self.limit, self.period, self._clock = limit, period, clock
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str) -> float:
        """Record a hit; returns 0 when allowed, else seconds until a slot frees up."""
        now = self._clock()
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= now - self.period:
                hits.popleft()
            if len(hits) >= self.limit:
                return max(1.0, hits[0] + self.period - now)
            hits.append(now)
            return 0.0


def require_oib(oib: str) -> str:
    """422 for a malformed OIB or a wrong checksum - before any database or external call."""
    if not is_valid_oib(oib):
        raise HTTPException(
            status_code=422,
            detail="Neispravan OIB: mora imati 11 znamenki i ispravnu kontrolnu znamenku.",
        )
    return oib


def require_cpv(value: str) -> str:
    """422 unless ``value`` is an 8-digit CPV code (optional check digit) or a 2-8 digit prefix."""
    if not CPV_RE.match(value):
        raise HTTPException(
            status_code=422,
            detail="Neispravan CPV: očekuje se 8 znamenki (npr. 45000000-7) ili prefiks od 2 do 8 znamenki.",
        )
    return value


def require_county(code: int | None) -> int | None:
    """422 unless ``code`` is one of the fixed county codes."""
    if code is not None and code not in valid_county_codes():
        raise HTTPException(
            status_code=422, detail=f"Nepoznata županija; dopuštene šifre: {valid_county_codes()}"
        )
    return code


class SoundingRequest(BaseModel):
    """Body of ``POST /sounding``: free text or a CPV code/prefix, plus a county."""

    text: str | None = Field(default=None, max_length=MAX_TEXT)
    cpv: str | None = None
    county: int | None = None

    @field_validator("text")
    @classmethod
    def _strip(cls, v: str | None) -> str | None:
        v = v.strip() if v else v
        return v or None


def make_router(
    get_session: Callable[..., Any],
    settings: NabavaSettings,
    engine: MatchEngine,
    lookup: LookupQueue,
    encode_queries: Callable[[list[str]], Any] | None = None,
) -> APIRouter:
    """Build the ``/api/v1`` router."""
    router = APIRouter(prefix="/api/v1")
    match_limit = SlidingLimit(MATCH_LIMIT_PER_MIN)
    environment = "test" if settings.sudreg_is_test else "production"

    def _encode(texts: list[str]) -> Any:
        if encode_queries is not None:
            return encode_queries(texts)
        from opendata_core import semantic

        return semantic.encode_queries(texts)

    # ------------------------------------------------------------------ company
    @router.get("/company/{oib}")
    def get_company(oib: str, session: Session = Depends(get_session)) -> Any:
        require_oib(oib)
        profile = company_profile(session, oib)
        if profile is None:
            if not settings.sudreg_client_id:
                raise HTTPException(
                    503, "Pristup Sudskom registru nije podešen (SUDREG_CLIENT_ID)."
                )
            job = lookup.submit(oib)
            job.event.wait(timeout=LOOKUP_WAIT_S)
            if job.status == "done":
                session.expire_all()
                profile = company_profile(session, oib)
            elif not job.finished:
                wait = lookup.retry_after()
                return JSONResponse(
                    {
                        "status": "queued",
                        "oib": oib,
                        "retry_after": wait,
                        "detail": "Upit prema Sudskom registru je u redu čekanja (ograničenje 6 upita u minuti).",
                    },
                    status_code=202,
                    headers={"Retry-After": str(wait)},
                )
            elif job.status == "excluded":
                raise HTTPException(
                    404, "Subjekt nije u obuhvatu (trgovac pojedinac, stečaj ili likvidacija)."
                )
            elif job.status == "unavailable":
                raise HTTPException(503, "Sudski registar trenutno nije dostupan za ovaj upit.")
            elif job.status == "error":
                raise HTTPException(502, "Greška pri dohvatu iz Sudskog registra.")
        if profile is None:
            raise HTTPException(404, "Tvrtka s tim OIB-om nije pronađena u Sudskom registru.")
        return {**profile, "source": {"id": "sudreg", "environment": environment}}

    # ------------------------------------------------------------------ match
    @router.get("/match")
    def match(
        request: Request,
        oib: Annotated[str | None, Query(min_length=11, max_length=11)] = None,
        q: Annotated[str | None, Query(max_length=MAX_TEXT)] = None,
        county: int | None = None,
        deadline_min_days: Annotated[float, Query(ge=0, le=365)] = 0.0,
        limit: Annotated[int, Query(ge=1, le=100)] = 20,
        value_min: Annotated[float | None, Query(ge=0)] = None,
        value_max: Annotated[float | None, Query(ge=0)] = None,
        session: Session = Depends(get_session),
    ) -> Any:
        if oib is None and not (q and q.strip()):
            raise HTTPException(422, "Navedite OIB tvrtke ili opis djelatnosti (q).")
        if oib is not None:
            require_oib(oib)
        require_county(county)
        wait = match_limit.check(request.client.host if request.client else "unknown")
        if wait > 0:
            return problem(
                request,
                429,
                detail="Ograničenje: najviše 30 upita u minuti na /match.",
                headers={"Retry-After": str(int(wait))},
            )
        try:
            activities, company_nuts3, ranked = build_profile(session, oib=oib, q=q, encode=_encode)
        except CompanyNotLoaded as exc:
            raise HTTPException(
                404, "Tvrtka nije učitana; prvo pozovite /api/v1/company/{oib}."
            ) from exc
        if not activities:
            return []
        return engine.match(
            session,
            activities=activities,
            company_nuts3=company_nuts3,
            ranked_divisions=ranked,
            county=county,
            deadline_min_days=deadline_min_days,
            value_min=value_min,
            value_max=value_max,
            limit=limit,
        )

    # ------------------------------------------------------------------ notices
    @router.get("/notices/{pub_no}")
    def get_notice(pub_no: str, session: Session = Depends(get_session)) -> Any:
        notice = session.get(Notice, pub_no)
        if notice is None:
            raise HTTPException(404, "Obavijest nije pronađena.")
        nuts2 = (notice.buyer_nuts or notice.place_nuts or "")[:4] or None
        group = notice.cpv_main[:3] if notice.cpv_main else None
        awards = []
        if notice.type == "result":
            rows = session.execute(
                select(Award, Company.oib.label("known"))
                .join(Company, Company.oib == Award.winner_national_id, isouter=True)
                .where(Award.pub_no == pub_no)
                .order_by(Award.lot_id, Award.seq)
            ).all()
            awards = [
                {
                    "lot_id": a.lot_id,
                    "lot_status": a.lot_status,
                    # winners are named only when they are registered companies (no natural persons)
                    "winner": a.winner_name if known else None,
                    "winner_oib": a.winner_national_id if known else None,
                    "received_submissions": a.received_submissions,
                }
                for a, known in rows
            ]
        return {
            "pub_no": notice.pub_no,
            "type": notice.type,
            "notice_type": notice.notice_type,
            "pub_date": notice.pub_date.isoformat(),
            "procedure_id": notice.procedure_id,
            "title": notice.title,
            "description": notice.description,
            "buyer": notice.buyer_name,
            "buyer_nuts": notice.buyer_nuts,
            "place_nuts": notice.place_nuts,
            "cpv_codes": notice.cpv_codes,
            "cpv_main": notice.cpv_main,
            "deadline": notice.deadline.isoformat() if notice.deadline else None,
            "value_eur": float(notice.value_eur) if notice.value_eur is not None else None,
            "currency": notice.currency,
            "n_lots": notice.n_lots,
            "url_html": notice.url_html,
            "url_pdf": notice.url_pdf,
            "retrieved_at": notice.retrieved_at.isoformat() if notice.retrieved_at else None,
            "competition": competition_for(session, group, nuts2),
            "awards": awards,
        }

    # ------------------------------------------------------------------ competition
    @router.get("/competition")
    def competition(
        cpv: str,
        nuts2: str | None = None,
        session: Session = Depends(get_session),
    ) -> Any:
        require_cpv(cpv)
        if nuts2 is not None and nuts2 not in NUTS2_CODES:
            raise HTTPException(422, f"Nepoznata NUTS2 regija; dopuštene: {NUTS2_CODES}")
        prefix = effective_prefix(cpv)
        if len(prefix) >= 3:
            return competition_for(session, prefix[:3], nuts2)
        rows = session.scalars(
            select(CompetitionStat)
            .where(
                CompetitionStat.nuts2 == (nuts2 or "HR"),
                CompetitionStat.cpv_group.like(f"{prefix}%"),
            )
            .order_by(CompetitionStat.n_awards.desc())
        ).all()
        return {
            "division": prefix,
            "scope": nuts2 or "HR",
            "groups": [competition_for(session, r.cpv_group, nuts2) for r in rows],
        }

    # ------------------------------------------------------------------ sounding
    @router.post("/sounding")
    def sounding(body: SoundingRequest, session: Session = Depends(get_session)) -> Any:
        if bool(body.text) == bool(body.cpv):
            raise HTTPException(
                422, "Navedite točno jedno: opis nabave (text) ili CPV šifru (cpv)."
            )
        if body.cpv:
            require_cpv(body.cpv)
        require_county(body.county)
        return sound_market(
            session, text_input=body.text, cpv=body.cpv, county=body.county, encode=_encode
        )

    # ------------------------------------------------------------------ validation, helpers
    @router.get("/validation")
    def validation(session: Session = Depends(get_session)) -> Any:
        row = session.get(Calibration, EVAL_KEY)
        if row is None:
            raise HTTPException(404, "Validacija još nije provedena (nabavaradar eval).")
        return {**row.value, "stored_at": row.updated_at.isoformat()}

    @router.get("/municipal/coverage")
    def municipal_coverage(session: Session = Depends(get_session)) -> Any:
        """P1: how many municipal registers were found, parsed and rejected (and why)."""
        row = session.get(Calibration, "municipal_coverage")
        if row is None:
            raise HTTPException(
                404, "Registri ugovora još nisu učitani (nabavaradar ingest municipal)."
            )
        return {**row.value, "stored_at": row.updated_at.isoformat()}

    @router.get("/counties")
    def list_counties() -> Any:
        return [
            {"code": c.code, "name": c.name, "nuts3": c.nuts3, "nuts2": c.nuts2} for c in counties()
        ]

    @router.get("/cpv")
    def search_cpv(
        q: Annotated[str, Query(min_length=2, max_length=100)],
        limit: Annotated[int, Query(ge=1, le=50)] = 15,
        session: Session = Depends(get_session),
    ) -> Any:
        """CPV picker: search by code prefix or label text."""
        like = f"%{q.strip()}%"
        stmt = select(Cpv.code, Cpv.check_digit, Cpv.label_hr, Cpv.label_en)
        if q.strip().isdigit():
            stmt = stmt.where(Cpv.code.like(f"{q.strip()}%"))
        else:
            stmt = stmt.where(Cpv.label_hr.ilike(like) | Cpv.label_en.ilike(like))
        rows = session.execute(stmt.order_by(Cpv.code).limit(limit)).all()
        return [
            {
                "code": r.code,
                "check_digit": r.check_digit,
                "label": r.label_hr or r.label_en,
                "division": r.code[:2],
                "group": r.code[:3],
            }
            for r in rows
        ]

    @router.get("/status")
    def status(session: Session = Depends(get_session)) -> Any:
        """Counts and data dates for the UI footer."""
        return {
            "environment": environment,
            "companies": session.scalar(select(func.count()).select_from(Company)),
            **data_dates(session),
        }

    return router
