"""The fixed list of Croatian counties and their NUTS codes (config/counties.yaml)."""

from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

import yaml

CONFIG_DIR = Path(__file__).parent / "config"


@dataclass(frozen=True)
class County:
    """A county with its DGU code (as used by the Sudski registar) and NUTS codes."""

    code: int
    name: str
    nuts3: str
    nuts2: str


@lru_cache
def counties() -> tuple[County, ...]:
    """All 21 counties incl. Grad Zagreb, ordered by code."""
    raw = yaml.safe_load((CONFIG_DIR / "counties.yaml").read_text(encoding="utf-8"))
    return tuple(County(**c) for c in raw["counties"])


def by_code(code: int | None) -> County | None:
    """County for a DGU code, or ``None`` (unknown or foreign)."""
    if code is None:
        return None
    return next((c for c in counties() if c.code == code), None)


def by_nuts3(nuts3: str | None) -> County | None:
    """County for a NUTS3 code."""
    if not nuts3:
        return None
    return next((c for c in counties() if c.nuts3 == nuts3), None)


def valid_county_codes() -> list[int]:
    """The DGU county codes accepted by the API."""
    return [c.code for c in counties()]


def nuts2_of(nuts: str | None) -> str | None:
    """NUTS2 (four characters) of a NUTS3 code; ``None`` for anything that is not HR + 3 chars."""
    if nuts and len(nuts) >= 4 and nuts.startswith("HR"):
        return nuts[:4]
    return None
