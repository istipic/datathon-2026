"""Name normalisation and fuzzy joining (kindergarten register <-> free-places table)."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

from rapidfuzz import fuzz, process

MATCH_THRESHOLD = 90.0
# Words that identify the kind of institution, not the institution ("DV Bajka" == "BAJKA").
STOP_TOKENS = frozenset({"dv", "djecji", "vrtic", "vrtici", "gradski", "dj"})


def normalise_name(name: str) -> str:
    """Lower-case, strip diacritics (incl. đ), keep alphanumerics, drop institution-type words."""
    text = name.lower().replace("đ", "d")
    text = "".join(
        ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)
    )
    tokens = re.findall(r"[a-z0-9]+", text)
    return " ".join(t for t in tokens if t not in STOP_TOKENS)


@dataclass(frozen=True)
class Match:
    """Best register match for one name (``right_index`` is None below the threshold)."""

    left_index: int
    right_index: int | None
    score: float


def fuzzy_join(
    left: list[str], right: list[str], threshold: float = MATCH_THRESHOLD
) -> list[Match]:
    """For every name in ``left`` the best match in ``right`` by ``token_sort_ratio`` on normalised
    names; below ``threshold`` the match is ``None`` (the row stays unmatched, never forced)."""
    right_norm = [normalise_name(r) for r in right]
    out: list[Match] = []
    for i, name in enumerate(left):
        found = process.extractOne(
            normalise_name(name), right_norm, scorer=fuzz.token_sort_ratio, score_cutoff=threshold
        )
        out.append(
            Match(i, None, 0.0) if found is None else Match(i, int(found[2]), float(found[1]))
        )
    return out
