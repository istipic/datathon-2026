"""Fit between a company and a tender: Fit = 0.55*S + 0.25*C + 0.10*G + 0.10*T (all in 0-1).

- S: best cosine between a company activity and the notice, rescaled with the 5th/95th percentile of
  all activity-notice cosines (stored at ingest);
- C: the notice's CPV division is among the company's top-3 (1.0) / top-10 (0.5) crosswalk divisions;
- G: geography - same NUTS3 1.0, same NUTS2 0.5, otherwise 0.2, unknown 0.5;
- T: time - >= 15 days to the deadline 1.0, linear to 0 at 3 days (expired notices are excluded).
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from nabavaradar_api.constants import WEIGHTS
from nabavaradar_api.counties import nuts2_of

T_FULL_DAYS = 15.0
T_ZERO_DAYS = 3.0
T_UNKNOWN = 0.5  # notice without a deadline: neutral
G_SAME_NUTS3, G_SAME_NUTS2, G_OTHER, G_UNKNOWN = 1.0, 0.5, 0.2, 0.5


@dataclass(frozen=True)
class Components:
    """The four fit components (0-1)."""

    S: float
    C: float
    G: float
    T: float

    def fit(self) -> float:
        """Weighted sum, rounded to 4 decimals."""
        return round(
            WEIGHTS["S"] * self.S + WEIGHTS["C"] * self.C + WEIGHTS["G"] * self.G + WEIGHTS["T"] * self.T,
            4,
        )


def rescale_similarity(cosine: float, p5: float, p95: float) -> float:
    """S: linear rescale of a cosine to 0-1 between the 5th and 95th percentile (clipped)."""
    if p95 <= p5:
        return 0.0
    return min(1.0, max(0.0, (cosine - p5) / (p95 - p5)))


def rank_divisions(per_activity: Iterable[Mapping[str, float]]) -> list[str]:
    """Company's CPV divisions ordered by their best similarity over all its activities."""
    best: dict[str, float] = {}
    for sims in per_activity:
        for division, sim in sims.items():
            if sim > best.get(division, float("-inf")):
                best[division] = sim
    return [d for d, _ in sorted(best.items(), key=lambda kv: (-kv[1], kv[0]))]


def crosswalk_component(division: str | None, ranked: Sequence[str]) -> float:
    """C: 1.0 for a top-3 division, 0.5 for top-10, else 0."""
    if not division or division not in ranked:
        return 0.0
    position = ranked.index(division)
    if position < 3:
        return 1.0
    return 0.5 if position < 10 else 0.0


def geography_component(buyer_nuts: str | None, company_nuts3: str | None) -> float:
    """G: same NUTS3 1.0, same NUTS2 0.5, otherwise 0.2; 0.5 when either side is unknown."""
    if not buyer_nuts or not company_nuts3:
        return G_UNKNOWN
    if buyer_nuts == company_nuts3:
        return G_SAME_NUTS3
    a, b = nuts2_of(buyer_nuts), nuts2_of(company_nuts3)
    if a is None or b is None:
        return G_UNKNOWN
    return G_SAME_NUTS2 if a == b else G_OTHER


def days_to_deadline(deadline: datetime | None, now: datetime) -> float | None:
    """Fractional days from ``now`` to the deadline; ``None`` when there is none."""
    if deadline is None:
        return None
    return (deadline - now).total_seconds() / 86400.0


def time_component(days: float | None) -> float | None:
    """T: 1 at >= 15 days, linear down to 0 at 3 days; ``None`` for an expired notice (excluded)."""
    if days is None:
        return T_UNKNOWN
    if days < 0:
        return None
    if days >= T_FULL_DAYS:
        return 1.0
    if days <= T_ZERO_DAYS:
        return 0.0
    return (days - T_ZERO_DAYS) / (T_FULL_DAYS - T_ZERO_DAYS)
