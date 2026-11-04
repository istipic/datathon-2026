"""Bulk load of the register into ``company``, ``company_activity`` and ``nkd``.

All reads are pinned to one snapshot (developer guide: otherwise tables could come from different
daily snapshots). Only company-level fields are kept; sole traders ("trgovac pojedinac", whose name
is usually a natural person's), bankruptcy/liquidation subjects and estates are skipped.
"""

from __future__ import annotations

from collections import Counter
from datetime import datetime
from typing import Any

import structlog
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session

from nabavaradar_api.constants import SRC_SUDREG
from nabavaradar_api.db import Company, CompanyActivity, Nkd
from nabavaradar_api.oib import is_valid_oib, normalise_oib
from nabavaradar_api.settings import NabavaSettings
from nabavaradar_api.sudreg.client import Snapshot, SudregClient
from nabavaradar_api.sudreg.parse import (
    EXCLUDED_PROCEDURES,
    MAIN_ACTIVITY_VERSION,
    SOLE_TRADER_FORM,
    county_fields,
    nkd_code_from_number,
    parse_snapshot_time,
)
from opendata_core.provenance import record_ingestion

log = structlog.get_logger(__name__)

BATCH = 5000


def _upsert(
    session: Session, model: Any, rows: list[dict[str, Any]], keys: list[Any], update: list[str]
) -> None:
    for i in range(0, len(rows), BATCH):
        stmt = insert(model).values(rows[i : i + BATCH])
        stmt = stmt.on_conflict_do_update(
            index_elements=keys, set_={c: getattr(stmt.excluded, c) for c in update}
        )
        session.execute(stmt)


def choose_snapshot(client: SudregClient, snapshot_id: int | None) -> Snapshot:
    """The requested snapshot, else the freshest available one."""
    snaps = client.snapshots()
    if not snaps:
        raise RuntimeError("the register reports no snapshots")
    if snapshot_id is None:
        return snaps[0]
    for snap in snaps:
        if snap.id == snapshot_id:
            return snap
    raise ValueError(f"snapshot {snapshot_id} not available (have {[s.id for s in snaps]})")


def _current_entry(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """The current one of several register rows with the same (code, version): active first, then
    the latest ``vrijedi_od``, then the highest id."""
    return max(
        rows,
        key=lambda r: (
            1 if r.get("status") == 1 else 0,
            str(r.get("vrijedi_od") or ""),
            int(r["id"]),
        ),
    )


def ingest_nkd(
    session: Session, client: SudregClient, snapshot: Snapshot
) -> dict[int, tuple[str, str]]:
    """Load the NKD code list (all versions) and return ``{register id: (code, version)}``.

    The register keeps several rows per (code, version) (renamed entries); every id is mapped to
    its (code, version) so that activities pointing at an older row are not lost, while the stored
    label is the current one.
    """
    rows = client._get(
        "nacionalna_klasifikacija_djelatnosti",
        {"snapshot_id": snapshot.id, "history_columns": "true"},
    ).json()
    groups: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for r in rows:
        groups.setdefault((str(r["sifra"]), str(r["verzija"])), []).append(r)
    out: list[dict[str, Any]] = []
    id_to_key: dict[int, tuple[str, str]] = {}
    for key, group in groups.items():
        current = _current_entry(group)
        out.append(
            {
                "code": key[0],
                "version": key[1],
                "sudreg_id": int(current["id"]),
                "label_hr": str(current["puni_naziv"]).strip(),
            }
        )
        for r in group:
            id_to_key[int(r["id"])] = key
    _upsert(session, Nkd, out, [Nkd.code, Nkd.version], ["sudreg_id", "label_hr"])
    log.info(
        "nkd_loaded",
        entries=len(out),
        register_rows=len(rows),
        versions=dict(Counter(r["version"] for r in out)),
    )
    return id_to_key


def ingest_sudreg(
    session: Session, settings: NabavaSettings, *, snapshot_id: int | None = None
) -> dict[str, Any]:
    """Load the register snapshot; returns a report with counts."""
    report: dict[str, Any] = {}
    with SudregClient(settings) as client:
        snapshot = choose_snapshot(client, snapshot_id)
        snap_at = parse_snapshot_time(snapshot.timestamp)
        url = f"{settings.sudreg_base_url}/ (snapshot_id={snapshot.id})"
        with record_ingestion(session, SRC_SUDREG, url) as run:
            run.source_last_modified = snap_at
            nkd_by_id = ingest_nkd(session, client, snapshot)

            sole_trader_ids = {
                int(r["id"])
                for r in client._get("vrste_pravnih_oblika", {"snapshot_id": snapshot.id}).json()
                if r.get("sifra") == SOLE_TRADER_FORM
            }
            forms: dict[int, int] = {}
            for page in client.table("pravni_oblici", snapshot.id):
                for r in page:
                    forms[int(r["mbs"])] = int(r["vrsta_pravnog_oblika_id"])

            skipped: Counter[str] = Counter()
            subjects: dict[int, dict[str, Any]] = {}
            for page in client.table("subjekti", snapshot.id):
                for r in page:
                    mbs = int(r["mbs"])
                    oib = normalise_oib(r["oib"]) if r.get("oib") else None
                    if not oib or not is_valid_oib(oib):
                        skipped["no_valid_oib"] += 1
                    elif int(r.get("status", 0)) != 1:
                        skipped["inactive"] += 1
                    elif r.get("stecajna_masa") or r.get("likvidacijska_masa"):
                        skipped["estate"] += 1
                    elif int(r.get("postupak") or 1) in EXCLUDED_PROCEDURES:
                        skipped["bankruptcy_or_liquidation"] += 1
                    elif forms.get(mbs) in sole_trader_ids:
                        skipped["sole_trader"] += 1
                    else:
                        subjects[mbs] = {"oib": oib, "glavna": r.get("glavna_djelatnost")}
            report["subjects_total_read"] = len(subjects) + sum(skipped.values())
            report["skipped"] = dict(skipped)

            names: dict[int, str] = {}
            for page in client.table("tvrtke", snapshot.id):
                for r in page:
                    if int(r["mbs"]) in subjects:
                        names[int(r["mbs"])] = str(r["ime"]).strip()
            seats: dict[int, int | None] = {}
            for page in client.table("sjedista", snapshot.id):
                for r in page:
                    if int(r["mbs"]) in subjects:
                        seats[int(r["mbs"])] = r.get("sifra_zupanije")

            # activities: main (glavna_djelatnost, NKD 2007) + pretezite + NKD-coded predmeti/evidencijske
            activities: dict[int, dict[tuple[str, str], bool]] = {m: {} for m in subjects}
            for mbs, s in subjects.items():
                if s["glavna"]:
                    activities[mbs][(nkd_code_from_number(s["glavna"]), MAIN_ACTIVITY_VERSION)] = (
                        True
                    )
            has_main = {m for m, a in activities.items() if a}
            unknown_nkd = 0
            for table, mark_main in (
                ("pretezite_djelatnosti", True),
                ("predmeti_poslovanja", False),
                ("evidencijske_djelatnosti", False),
            ):
                for page in client.table(table, snapshot.id):
                    for r in page:
                        mbs = int(r["mbs"])
                        nid = r.get("nacionalna_klasifikacija_djelatnosti_id")
                        if mbs not in subjects or not nid:
                            continue
                        key = nkd_by_id.get(int(nid))
                        if key is None:
                            unknown_nkd += 1
                            continue
                        # a main activity from pretezite only counts when glavna_djelatnost is absent
                        is_main = mark_main and mbs not in has_main
                        activities[mbs].setdefault(key, False)
                        if is_main:
                            activities[mbs][key] = True
                log.info("activities_read", table=table)
            report["unknown_nkd_refs"] = unknown_nkd

            company_rows: list[dict[str, Any]] = []
            for mbs, s in subjects.items():
                county, nuts3 = county_fields(seats.get(mbs))
                company_rows.append(
                    {
                        "oib": s["oib"],
                        "mbs": mbs,
                        "name": names.get(mbs, ""),
                        "status": 1,
                        "county_code": county,
                        "nuts3": nuts3,
                        "updated_snapshot": snapshot.id,
                        "snapshot_at": snap_at,
                    }
                )
            # one OIB must map to one company: keep the first MBS if the register repeats an OIB
            dedup = {r["oib"]: r for r in company_rows}
            company_rows = list(dedup.values())
            oib_by_mbs = {r["mbs"]: r["oib"] for r in company_rows}
            _upsert(
                session,
                Company,
                company_rows,
                [Company.oib],
                [
                    "mbs",
                    "name",
                    "status",
                    "county_code",
                    "nuts3",
                    "updated_snapshot",
                    "snapshot_at",
                ],
            )
            session.execute(delete(CompanyActivity))
            act_rows = [
                {"oib": oib_by_mbs[m], "nkd_code": code, "nkd_version": ver, "is_main": main}
                for m, acts in activities.items()
                if m in oib_by_mbs
                for (code, ver), main in acts.items()
            ]
            _upsert(
                session,
                CompanyActivity,
                act_rows,
                [CompanyActivity.oib, CompanyActivity.nkd_code, CompanyActivity.nkd_version],
                ["is_main"],
            )
            # remove companies that are no longer in this snapshot (closed, bankrupt, ...)
            stale = session.execute(delete(Company).where(Company.updated_snapshot != snapshot.id))
            report["removed_stale_companies"] = stale.rowcount
            with_nkd = len({r["oib"] for r in act_rows})
            run.rows = len(company_rows)
            report.update(
                snapshot_id=snapshot.id,
                snapshot_timestamp=snapshot.timestamp,
                companies=len(company_rows),
                activities=len(act_rows),
                companies_with_nkd=with_nkd,
                nkd_coverage=round(with_nkd / max(1, len(company_rows)), 4),
            )
    n = session.scalar(select(func.count()).select_from(Company))
    log.info("sudreg_loaded", **report, companies_in_db=n)
    return report


def parse_ts(value: str | None) -> datetime | None:
    """Re-export for tests."""
    return parse_snapshot_time(value)
