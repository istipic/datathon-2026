"""Hot days and tropical nights from Open-Meteo Climate API daily series (pure functions).

Hot day: Tmax >= 30 C. Tropical night: Tmin >= 20 C. Per model the mean annual count is taken over
the years of a window; a year counts only when at least ``MIN_VALID_DAYS`` of its days have a value
(one model returns a gap of one year, which must not drag the mean down).
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Sequence
from typing import Any

from otporno_api.constants import BASE_YEARS, FUT_YEARS, HOT_DAY_C, MODELS, TROPICAL_NIGHT_C

MIN_VALID_DAYS = 300


def annual_counts(
    times: Sequence[str],
    values: Sequence[float | None],
    threshold: float,
    first_year: int,
    last_year: int,
    *,
    min_valid_days: int = MIN_VALID_DAYS,
) -> dict[int, int]:
    """Number of days with ``value >= threshold`` per year in ``[first_year, last_year]``.

    Years with fewer than ``min_valid_days`` valid values are left out.
    """
    hot: dict[int, int] = defaultdict(int)
    valid: dict[int, int] = defaultdict(int)
    for t, v in zip(times, values, strict=True):
        year = int(t[:4])
        if year < first_year or year > last_year or v is None:
            continue
        valid[year] += 1
        if v >= threshold:
            hot[year] += 1
    return {y: hot[y] for y in valid if valid[y] >= min_valid_days}


def mean_annual(
    times: Sequence[str],
    values: Sequence[float | None],
    threshold: float,
    window: tuple[int, int],
) -> float | None:
    """Mean annual count over the usable years of ``window`` (``None`` if no year is usable)."""
    counts = annual_counts(times, values, threshold, window[0], window[1])
    return sum(counts.values()) / len(counts) if counts else None


def model_metrics(daily: dict[str, Any], model: str) -> dict[str, float | None]:
    """Base (1991-2020) and future (2031-2050) hot days and tropical nights of one model."""
    times = daily["time"]
    tmax = daily.get(f"temperature_2m_max_{model}")
    tmin = daily.get(f"temperature_2m_min_{model}")
    out: dict[str, float | None] = {
        "base_hot_days": None,
        "fut_hot_days": None,
        "base_trop_nights": None,
        "fut_trop_nights": None,
    }
    if tmax is not None:
        out["base_hot_days"] = mean_annual(times, tmax, HOT_DAY_C, BASE_YEARS)
        out["fut_hot_days"] = mean_annual(times, tmax, HOT_DAY_C, FUT_YEARS)
    if tmin is not None:
        out["base_trop_nights"] = mean_annual(times, tmin, TROPICAL_NIGHT_C, BASE_YEARS)
        out["fut_trop_nights"] = mean_annual(times, tmin, TROPICAL_NIGHT_C, FUT_YEARS)
    return out


def all_models(
    daily: dict[str, Any], models: Sequence[str] = MODELS
) -> dict[str, dict[str, float | None]]:
    """``model_metrics`` for every requested model that is present in the response."""
    return {
        m: model_metrics(daily, m)
        for m in models
        if f"temperature_2m_max_{m}" in daily or f"temperature_2m_min_{m}" in daily
    }


def ensemble(values: Sequence[float | None]) -> tuple[float, float, float] | None:
    """(mean, min, max) across models, ignoring missing values; ``None`` if nothing is left."""
    vals = [v for v in values if v is not None]
    if not vals:
        return None
    return sum(vals) / len(vals), min(vals), max(vals)
