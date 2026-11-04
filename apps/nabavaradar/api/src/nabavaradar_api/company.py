"""Company profiles: from the database, else a live ``detalji_subjekta`` lookup through a queue.

The queue has a single worker that honours the 6 calls/minute limit of the register. A request that
cannot be answered within a short wait gets ``202`` and a ``Retry-After`` estimate instead of
blocking; the same OIB asked again later finds the stored result.
"""

from __future__ import annotations

import queue
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from typing import Any

import structlog
from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, sessionmaker

from nabavaradar_api.counties import by_code
from nabavaradar_api.db import Company, CompanyActivity, Nkd
from nabavaradar_api.settings import NabavaSettings
from nabavaradar_api.sudreg.client import (
    DETALJI_LIMIT,
    DETALJI_PERIOD_S,
    SudregAuthError,
    SudregClient,
    SudregError,
    SudregNotFound,
)
from nabavaradar_api.sudreg.parse import CompanyRecord, exclusion_reason, parse_detail

log = structlog.get_logger(__name__)

MAX_JOBS = 500


def company_profile(session: Session, oib: str) -> dict[str, Any] | None:
    """Stored profile (company-level fields only) or ``None``."""
    company = session.get(Company, oib)
    if company is None:
        return None
    acts = session.execute(
        select(
            CompanyActivity.nkd_code,
            CompanyActivity.nkd_version,
            CompanyActivity.is_main,
            Nkd.label_hr,
        )
        .join(
            Nkd,
            (Nkd.code == CompanyActivity.nkd_code) & (Nkd.version == CompanyActivity.nkd_version),
            isouter=True,
        )
        .where(CompanyActivity.oib == oib)
        .order_by(
            CompanyActivity.is_main.desc(),
            CompanyActivity.nkd_version.desc(),
            CompanyActivity.nkd_code,
        )
    ).all()
    county = by_code(company.county_code)
    return {
        "oib": company.oib,
        "mbs": company.mbs,
        "name": company.name,
        "status": company.status,
        "county": {"code": county.code, "name": county.name, "nuts3": county.nuts3}
        if county
        else None,
        "activities": [
            {
                "code": a.nkd_code,
                "version": a.nkd_version,
                "label": a.label_hr,
                "is_main": bool(a.is_main),
            }
            for a in acts
        ],
        "data_as_of": company.snapshot_at.isoformat() if company.snapshot_at else None,
        "snapshot_id": company.updated_snapshot,
        "retrieved_at": company.retrieved_at.isoformat() if company.retrieved_at else None,
    }


def store_company(session: Session, record: CompanyRecord) -> None:
    """Upsert a company and replace its activities."""
    values = {
        "oib": record.oib,
        "mbs": record.mbs,
        "name": record.name,
        "status": record.status,
        "county_code": record.county_code,
        "nuts3": record.nuts3,
        "updated_snapshot": record.snapshot_id or 0,
        "snapshot_at": record.snapshot_at,
    }
    stmt = insert(Company).values(values)
    session.execute(
        stmt.on_conflict_do_update(
            index_elements=[Company.oib], set_={k: stmt.excluded[k] for k in values if k != "oib"}
        )
    )
    session.execute(delete(CompanyActivity).where(CompanyActivity.oib == record.oib))
    rows = [
        {"oib": record.oib, "nkd_code": c, "nkd_version": v, "is_main": m}
        for c, v, m in record.activities
    ]
    if rows:
        session.execute(insert(CompanyActivity).values(rows).on_conflict_do_nothing())
    session.commit()


@dataclass
class Job:
    """State of one live lookup."""

    oib: str
    status: str = "queued"  # queued | running | done | not_found | excluded | unavailable | error
    detail: str | None = None
    created: float = field(default_factory=time.monotonic)
    event: threading.Event = field(default_factory=threading.Event)

    @property
    def finished(self) -> bool:
        """True once the worker is done with the job (successfully or not)."""
        return self.status not in ("queued", "running")


class LookupQueue:
    """Single-worker queue for live register lookups (6/minute)."""

    def __init__(
        self,
        settings: NabavaSettings,
        session_factory: sessionmaker[Session],
        client: SudregClient | None = None,
    ) -> None:
        self.settings = settings
        self._factory = session_factory
        self._client = client
        self._queue: queue.Queue[Job] = queue.Queue()
        self._jobs: OrderedDict[str, Job] = OrderedDict()
        self._lock = threading.Lock()
        self._thread: threading.Thread | None = None

    @property
    def client(self) -> SudregClient:
        """The register client (created lazily so start-up needs no credentials)."""
        if self._client is None:
            self._client = SudregClient(self.settings)
        return self._client

    def start(self) -> None:
        """Start the worker thread (idempotent)."""
        if self._thread is None:
            self._thread = threading.Thread(target=self._work, name="sudreg-lookup", daemon=True)
            self._thread.start()

    def submit(self, oib: str) -> Job:
        """Queue a lookup (or return the one already queued/finished recently)."""
        with self._lock:
            job = self._jobs.get(oib)
            if job is not None and (not job.finished or time.monotonic() - job.created < 30):
                return job
            job = Job(oib)
            self._jobs[oib] = job
            while len(self._jobs) > MAX_JOBS:
                self._jobs.popitem(last=False)
        self._queue.put(job)
        self.start()
        return job

    def retry_after(self) -> int:
        """Rough seconds until a job queued now would be processed."""
        per_call = DETALJI_PERIOD_S / DETALJI_LIMIT
        wait = self.client.limiter.peek() if self._client else 0.0
        return max(5, round(wait + self._queue.qsize() * per_call + 2))

    def _work(self) -> None:
        while True:
            job = self._queue.get()
            job.status = "running"
            try:
                body = self.client.detalji_subjekta(job.oib, wait=True)
                reason = exclusion_reason(body)
                record = None if reason else parse_detail(body)
                if reason:
                    job.status, job.detail = "excluded", reason
                elif record is None:
                    job.status, job.detail = "not_found", "no valid OIB in the register response"
                else:
                    with self._factory() as session:
                        store_company(session, record)
                    job.status = "done"
            except SudregNotFound:
                job.status = "not_found"
            except SudregAuthError as exc:
                job.status, job.detail = "unavailable", str(exc)
            except (SudregError, Exception) as exc:  # noqa: BLE001 - never kill the worker thread
                log.warning("lookup_failed", error=type(exc).__name__)
                job.status, job.detail = "error", type(exc).__name__
            finally:
                job.event.set()
