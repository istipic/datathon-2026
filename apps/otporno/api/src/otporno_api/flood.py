"""Flood: level from scenario flags, and the state of the data access ladder.

Hrvatske vode publish the 2019 hazard maps only as WMS images (docs/adr/0007, evidence
``2026-11-04_hv_flood_ladder_summary.json``): the hazard layers are not queryable, WFS is disabled and no
vector download exists. The app therefore runs on ladder step c): the WMS is an overlay, the flood level
is ``None`` and the message tells people to look at the map. A class is NEVER derived from pixel colours.

``flood_level`` is the classification rule; it is only fed with real flags if a vector or point-query
source becomes available (ladder a or b).
"""

from __future__ import annotations

from dataclasses import dataclass

from otporno_api.constants import (
    FLOOD_DISCLAIMER,
    FLOOD_MAP_YEAR,
    FLOOD_UNAVAILABLE,
    HV_LAYERS,
)
from otporno_api.settings import OtpornoSettings

LEVEL_SCORE = {3: 1.0, 2: 0.66, 1: 0.33, 0: 0.0}
LADDER = "c"  # a) vector polygons  b) GetFeatureInfo  c) WMS overlay only


def flood_level(high: bool, medium: bool, low: bool) -> int:
    """3 inside the high-probability scenario, 2 medium, 1 low, 0 none."""
    if high:
        return 3
    if medium:
        return 2
    if low:
        return 1
    return 0


def flood_score(level: int | None) -> float | None:
    """Score 1.0 / 0.66 / 0.33 / 0 of a level (``None`` stays ``None``)."""
    return None if level is None else LEVEL_SCORE[level]


def level_from_cell_shares(
    share_high: float, share_medium: float, share_low: float, threshold: float = 0.10
) -> int:
    """Cell level (ladder a): the highest scenario that covers at least ``threshold`` of the cell."""
    if share_high >= threshold:
        return 3
    if share_medium >= threshold:
        return 2
    if share_low >= threshold:
        return 1
    return 0


@dataclass(frozen=True)
class FloodResult:
    """What the passport says about flood."""

    level: int | None
    band: str | None
    scenarios: dict[str, bool | None]
    method: str
    message: str | None


def assess(scenarios: dict[str, bool | None] | None = None) -> FloodResult:
    """Flood assessment from scenario flags; without flags (ladder c) the level stays unknown."""
    flags = scenarios or {"high": None, "medium": None, "low": None}
    if any(v is None for v in flags.values()):
        return FloodResult(
            None,
            None,
            dict.fromkeys(("high", "medium", "low")),
            "wms-overlay-only",
            FLOOD_UNAVAILABLE,
        )
    level = flood_level(bool(flags["high"]), bool(flags["medium"]), bool(flags["low"]))
    return FloodResult(level, None, dict(flags), "scenario-flags", None)


def flood_payload(
    settings: OtpornoSettings, scenarios: dict[str, bool | None] | None = None
) -> dict[str, object]:
    """The ``flood`` object of ``GET /passport``."""
    r = assess(scenarios)
    return {
        "level": r.level,
        "band": r.band,
        "scenarios": r.scenarios,
        "method": r.method,
        "message": r.message,
        "map_year": FLOOD_MAP_YEAR,
        "disclaimer": FLOOD_DISCLAIMER,
        "wms": {"url": settings.hv_wms_url, "layers": HV_LAYERS},
        "ladder": LADDER,
    }
