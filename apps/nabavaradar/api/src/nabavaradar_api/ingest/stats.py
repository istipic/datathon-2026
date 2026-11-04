"""Competition statistics per CPV group (3 digits) and NUTS2 over the result window."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import structlog
from sqlalchemy import text
from sqlalchemy.orm import Session

from nabavaradar_api.constants import SINGLE_BID_FLAG_MIN_N, SINGLE_BID_FLAG_SHARE
from nabavaradar_api.settings import NabavaSettings

log = structlog.get_logger(__name__)

NATIONAL = "HR"

# One row per awarded lot (a lot with several winners counts once). The tenders received per lot
# come from the result notice; lots without the figure (legacy notices) are left out and n says so.
_STATS_SQL = text(
    """
    WITH lots AS (
        SELECT DISTINCT ON (a.pub_no, a.lot_id)
               substr(n.cpv_main, 1, 3) AS cpv_group,
               substr(coalesce(n.buyer_nuts, n.place_nuts), 1, 4) AS nuts2,
               a.received_submissions AS received
        FROM award a
        JOIN notice n ON n.pub_no = a.pub_no
        WHERE a.lot_status = 'selec-w'
          AND a.received_submissions IS NOT NULL AND a.received_submissions >= 1
          AND n.cpv_main IS NOT NULL
          AND n.pub_date >= :start AND n.pub_date <= :end
        ORDER BY a.pub_no, a.lot_id, a.seq
    ), scoped AS (
        SELECT cpv_group, nuts2, received FROM lots WHERE nuts2 LIKE 'HR0%'
        UNION ALL
        SELECT cpv_group, 'HR' AS nuts2, received FROM lots
    )
    SELECT cpv_group, nuts2,
           count(*) AS n_awards,
           percentile_cont(0.5) WITHIN GROUP (ORDER BY received) AS median_submissions,
           avg((received = 1)::int) AS single_bid_share
    FROM scoped
    GROUP BY cpv_group, nuts2
    """
)


def competition_flag(n_awards: int | None, single_bid_share: float | None) -> bool:
    """"Niska konkurencija": single-bid share >= 0.40 on at least 10 awards."""
    return (
        n_awards is not None
        and single_bid_share is not None
        and n_awards >= SINGLE_BID_FLAG_MIN_N
        and single_bid_share >= SINGLE_BID_FLAG_SHARE
    )


def compute_competition_stats(
    session: Session, settings: NabavaSettings, *, today: date | None = None
) -> dict[str, int | str]:
    """Recompute ``competition_stat`` for the last ``result_months`` months."""
    end = today or datetime.now(UTC).date()
    start = end - timedelta(days=round(settings.result_months * 30.4375))
    rows = session.execute(_STATS_SQL, {"start": start, "end": end}).all()
    session.execute(text("DELETE FROM competition_stat"))
    if rows:
        session.execute(
            text(
                "INSERT INTO competition_stat (cpv_group, nuts2, n_awards, median_submissions, "
                "single_bid_share, window_start, window_end) VALUES "
                "(:g, :n2, :n, :med, :sbs, :ws, :we)"
            ),
            [
                {
                    "g": r.cpv_group,
                    "n2": r.nuts2,
                    "n": r.n_awards,
                    "med": round(float(r.median_submissions), 2),
                    "sbs": round(float(r.single_bid_share), 5),
                    "ws": start,
                    "we": end,
                }
                for r in rows
            ],
        )
    session.commit()
    flagged = sum(1 for r in rows if competition_flag(r.n_awards, float(r.single_bid_share)))
    log.info("competition_stats", rows=len(rows), flagged=flagged, start=start.isoformat(), end=end.isoformat())
    return {"rows": len(rows), "flagged": flagged, "window_start": start.isoformat(), "window_end": end.isoformat()}
