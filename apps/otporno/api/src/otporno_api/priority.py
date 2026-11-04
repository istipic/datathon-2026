"""Cell priority and weights (pure functions).

priority = sum_h w_h * score_h * (pop_65p + 0.5 * (pop_total - pop_65p))

Defaults w_flood 0.5, w_heat 0.35, w_fire 0.15. A hazard whose score does not exist (flood today: the
data cannot be classified automatically; fire until it is loaded) contributes nothing and the remaining
weights are renormalised, so the priority stays on the same scale.
"""

from __future__ import annotations

from collections.abc import Mapping

from otporno_api.constants import CHILD_WORKING_AGE_FACTOR, DEFAULT_WEIGHTS

HAZARDS = ("flood", "heat", "fire")
TOLERANCE = 0.01


class WeightError(ValueError):
    """The weights are invalid (negative or not summing to 1 +- 0.01)."""


def validate_weights(weights: Mapping[str, float]) -> dict[str, float]:
    """Check non-negativity and a sum of 1 +- 0.01; returns a clean copy."""
    out = {h: float(weights.get(h, 0.0)) for h in HAZARDS}
    if any(v < 0 for v in out.values()):
        raise WeightError("težine ne smiju biti negativne")
    total = sum(out.values())
    if abs(total - 1.0) > TOLERANCE:
        raise WeightError(f"težine moraju imati zbroj 1 ± {TOLERANCE} (zbroj je {total:.3f})")
    return out


def effective_weights(
    weights: Mapping[str, float], available: Mapping[str, bool]
) -> dict[str, float]:
    """Weights of the hazards that have data, renormalised to sum 1 (all zero if none is available)."""
    kept = {h: weights[h] for h in HAZARDS if available.get(h) and weights[h] > 0}
    total = sum(kept.values())
    if total <= 0:
        return dict.fromkeys(HAZARDS, 0.0)
    return {h: (kept[h] / total if h in kept else 0.0) for h in HAZARDS}


def exposure_weight(pop_total: int | float | None, pop_65p: int | float | None) -> float:
    """People weighted by vulnerability: 65+ count fully, everybody else half."""
    total = float(pop_total or 0)
    old = min(float(pop_65p or 0), total)
    return old + CHILD_WORKING_AGE_FACTOR * (total - old)


def cell_priority(
    scores: Mapping[str, float | None],
    weights: Mapping[str, float],
    pop_total: int | float | None,
    pop_65p: int | float | None,
) -> float:
    """Priority of a cell from its hazard scores (``None`` = hazard not available)."""
    w = effective_weights(weights, {h: scores.get(h) is not None for h in HAZARDS})
    risk = sum(w[h] * float(scores[h] or 0.0) for h in HAZARDS)
    return risk * exposure_weight(pop_total, pop_65p)


def default_weights() -> dict[str, float]:
    """Default weights (flood 0.5, heat 0.35, fire 0.15)."""
    return dict(DEFAULT_WEIGHTS)
