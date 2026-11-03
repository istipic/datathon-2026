"""Scoring: walking minutes -> category score -> index, grade and confidence."""

from __future__ import annotations

import math
from collections.abc import Mapping
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).parent / "config"
DAYS_PER_MONTH = 30.4375


@dataclass(frozen=True)
class Persona:
    """A walking persona."""

    id: str
    label: str
    speed_mps: float
    graph: str  # "full" | "wheelchair"


@dataclass(frozen=True)
class Category:
    """A service category with its thresholds and per-persona weights."""

    id: str
    label: str
    good_min: float
    max_min: float
    group: str
    weights: Mapping[str, float]


@dataclass(frozen=True)
class ScoringConfig:
    """Parsed ``scoring.yaml``."""

    version: int
    updated: str
    personas: Mapping[str, Persona]
    categories: Mapping[str, Category]
    group_labels: Mapping[str, str]
    grades: Mapping[str, float]
    tier_factor: Mapping[str, float]
    freshness: tuple[tuple[float | None, float], ...]
    confidence_labels: Mapping[str, float]
    raw: Mapping[str, Any]


def parse_config(raw: Mapping[str, Any]) -> ScoringConfig:
    """Build a :class:`ScoringConfig` from the YAML mapping (validates basic consistency)."""
    personas = {
        pid: Persona(pid, p["label"], float(p["speed_mps"]), p["graph"])
        for pid, p in raw["personas"].items()
    }
    categories = {}
    for cid, c in raw["categories"].items():
        if not c["good_min"] < c["max_min"]:
            raise ValueError(f"category {cid}: good_min must be < max_min")
        missing = set(personas) - set(c["weights"])
        if missing:
            raise ValueError(f"category {cid}: missing weights for {sorted(missing)}")
        categories[cid] = Category(
            cid,
            c["label"],
            float(c["good_min"]),
            float(c["max_min"]),
            c["group"],
            {k: float(v) for k, v in c["weights"].items()},
        )
    conf = raw["confidence"]
    return ScoringConfig(
        version=int(raw["version"]),
        updated=str(raw["updated"]),
        personas=personas,
        categories=categories,
        group_labels=dict(raw["group_labels"]),
        grades={k: float(v) for k, v in raw["grades"].items()},
        tier_factor={k: float(v) for k, v in conf["tier_factor"].items()},
        freshness=tuple(
            (None if f["max_months"] is None else float(f["max_months"]), float(f["factor"]))
            for f in conf["freshness"]
        ),
        confidence_labels={k: float(v) for k, v in conf["labels"].items()},
        raw=raw,
    )


@lru_cache
def load_config(path: Path | None = None) -> ScoringConfig:
    """Load and cache the packaged ``scoring.yaml`` (or a given file)."""
    file = path or CONFIG_DIR / "scoring.yaml"
    return parse_config(yaml.safe_load(file.read_text(encoding="utf-8")))


def minutes(distance_m: float, speed_mps: float) -> float:
    """Walking minutes for a network distance."""
    return distance_m / speed_mps / 60.0


def score(t: float, good: float, maximum: float) -> float:
    """s(t) = 1 up to ``good`` minutes, 0 from ``maximum`` minutes, linear in between."""
    if t <= good:
        return 1.0
    if t >= maximum:
        return 0.0
    return (maximum - t) / (maximum - good)


def renormalised_index(items: list[tuple[float, float]]) -> int | None:
    """Index 0-100 from ``(weight, score)`` pairs of categories that have data.

    Weights are renormalised over the given pairs; pairs with weight 0 are ignored. Returns
    ``None`` when no weight remains.
    """
    total = sum(w for w, _ in items if w > 0)
    if total <= 0:
        return None
    value = 100.0 * sum(w * s for w, s in items if w > 0) / total
    return int(math.floor(value + 0.5))


def grade(index: int, grades: Mapping[str, float]) -> str:
    """Letter grade A-E for an index."""
    for letter in ("A", "B", "C", "D"):
        if index >= grades[letter]:
            return letter
    return "E"


def freshness_factor(days: float | None, bands: tuple[tuple[float | None, float], ...]) -> float:
    """Confidence factor for the age of the data (unknown age counts as the oldest band)."""
    if days is None:
        return bands[-1][1]
    months = days / DAYS_PER_MONTH
    for max_months, factor in bands:
        if max_months is None or months <= max_months:
            return factor
    return bands[-1][1]


def category_confidence(tier: str, days: float | None, cfg: ScoringConfig) -> float:
    """Tier factor x freshness factor."""
    return cfg.tier_factor.get(tier, cfg.tier_factor["community"]) * freshness_factor(
        days, cfg.freshness
    )


def overall_confidence(items: list[tuple[float, float]]) -> float | None:
    """Weighted mean of ``(weight, confidence)`` pairs; ``None`` if the total weight is 0."""
    total = sum(w for w, _ in items if w > 0)
    if total <= 0:
        return None
    return sum(w * c for w, c in items if w > 0) / total


def confidence_label(value: float, labels: Mapping[str, float]) -> str:
    """``visoka`` / ``srednja`` / ``niska`` for a confidence value."""
    if value >= labels["visoka"]:
        return "visoka"
    if value >= labels["srednja"]:
        return "srednja"
    return "niska"
