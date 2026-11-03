"""Free-text search over the nine categories ("tabletke" -> Ljekarna).

Semantic ranking (multilingual-e5-small via ``opendata_core.semantic``) when the optional extra is
installed and the model can be loaded; otherwise a keyword/fuzzy fallback. The method used is
returned with the results so the UI can be honest about it.
"""

from __future__ import annotations

import re
import threading
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import numpy as np
import structlog
import yaml
from rapidfuzz import fuzz

from blizu_api.scoring import CONFIG_DIR

log = structlog.get_logger(__name__)

MIN_SCORE_KEYWORD = 0.55
MIN_SCORE_SEMANTIC = (
    0.77  # empirical floor: e5 scores are compressed (nonsense queries score ~0.76)
)


def _fold(text: str) -> str:
    text = text.lower().replace("đ", "d")
    return "".join(
        ch for ch in unicodedata.normalize("NFKD", text) if not unicodedata.combining(ch)
    )


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", _fold(text))


@dataclass(frozen=True)
class CategoryText:
    """Descriptive text of one category."""

    id: str
    description: str
    synonyms: tuple[str, ...]

    @property
    def passage(self) -> str:
        return f"{self.description} {', '.join(self.synonyms)}"


@lru_cache
def load_category_texts(path: Path | None = None) -> tuple[CategoryText, ...]:
    """Parse ``config/categories_hr.yaml``."""
    raw = yaml.safe_load((path or CONFIG_DIR / "categories_hr.yaml").read_text(encoding="utf-8"))
    return tuple(
        CategoryText(cid, " ".join(str(c["description"]).split()), tuple(c["synonyms"]))
        for cid, c in raw["categories"].items()
    )


WORD_MATCH = 0.85  # a query word counts when it matches a category word at least this well
MIN_WORD_LEN = 3


def _contains_phrase(haystack: list[str], needle: list[str]) -> bool:
    """True if ``needle`` occurs as a contiguous run of whole words in ``haystack``."""
    n = len(needle)
    return n > 0 and any(haystack[k : k + n] == needle for k in range(len(haystack) - n + 1))


def keyword_scores(query: str, texts: tuple[CategoryText, ...]) -> dict[str, float]:
    """Score 0..1 per category: share of the query's content words that match a category word.

    A word matches by fuzzy similarity (>= 0.85) or as a prefix of a longer category word (>= 4
    letters: "tablet" ~ "tablete"). A whole synonym occurring in the query scores 1.0. Phrases are
    matched on whole words, never on substrings ("mlijeko" does not contain "lijek").
    """
    q_tokens = _tokens(query)
    out: dict[str, float] = {}
    for text in texts:
        vocab = set(_tokens(text.description)) | {tok for s in text.synonyms for tok in _tokens(s)}
        content = [t for t in q_tokens if len(t) >= MIN_WORD_LEN]
        matched = 0
        for tok in content:
            best = max((fuzz.ratio(tok, w) for w in vocab), default=0.0) / 100.0
            if len(tok) >= 4 and any(w.startswith(tok) for w in vocab):
                best = max(best, 0.9)
            matched += best >= WORD_MATCH
        score = matched / len(content) if content else 0.0
        phrase = any(_contains_phrase(q_tokens, _tokens(syn)) for syn in text.synonyms)
        out[text.id] = 1.0 if phrase else score
    return out


class CategorySearch:
    """Ranks categories for a query; thread-safe, model loaded lazily."""

    def __init__(
        self, texts: tuple[CategoryText, ...] | None = None, use_semantic: bool = True
    ) -> None:
        self.texts = texts or load_category_texts()
        self.use_semantic = use_semantic
        self._lock = threading.Lock()
        self._embeddings: np.ndarray | None = None
        self._semantic_failed = False

    def _semantic(self) -> Any | None:
        if not self.use_semantic or self._semantic_failed:
            return None
        with self._lock:
            if self._embeddings is None:
                try:
                    from opendata_core import semantic

                    self._embeddings = semantic.encode_passages([t.passage for t in self.texts])
                except Exception as exc:  # extra not installed / model not downloadable
                    log.warning("semantic_search_unavailable", error=str(exc)[:160])
                    self._semantic_failed = True
                    return None
        from opendata_core import semantic

        return semantic

    def warm_up(self) -> None:
        """Load the model now (called in a background thread at start-up)."""
        self._semantic()

    def search(self, query: str, top: int = 3) -> dict[str, Any]:
        """Top ``top`` categories with scores and the method used."""
        semantic = self._semantic()
        if semantic is not None and self._embeddings is not None:
            q = semantic.encode_queries([query])[0]
            sims = self._embeddings @ q
            ranked = sorted(zip(self.texts, sims.tolist(), strict=True), key=lambda t: -t[1])
            results = [(t.id, float(s)) for t, s in ranked[:top] if s >= MIN_SCORE_SEMANTIC]
            return self._payload("semantic", results)
        scores = keyword_scores(query, self.texts)
        ranked_kw = sorted(scores.items(), key=lambda kv: -kv[1])
        return self._payload(
            "keyword", [(c, s) for c, s in ranked_kw[:top] if s >= MIN_SCORE_KEYWORD]
        )

    @staticmethod
    def _payload(method: str, results: list[tuple[str, float]]) -> dict[str, Any]:
        return {
            "method": method,
            "results": [{"category": c, "score": round(s, 3)} for c, s in results],
        }
