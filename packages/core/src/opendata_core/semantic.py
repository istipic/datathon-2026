"""Multilingual sentence embeddings (optional extra: ``opendata-core[semantic]``).

Model: ``intfloat/multilingual-e5-small`` (384 dimensions). E5 models expect the prefixes
``"query: "`` / ``"passage: "``; they are added here. Embeddings are L2-normalised, so a dot
product equals cosine similarity.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np
from numpy.typing import NDArray

MODEL = "intfloat/multilingual-e5-small"
DIM = 384
BATCH_SIZE = 64

_model: Any = None


def _load() -> Any:
    """Lazy singleton: import and load the model on first use."""
    global _model
    if _model is None:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:  # pragma: no cover - depends on installed extras
            raise RuntimeError("semantic search needs the extra: uv sync --extra semantic") from exc
        _model = SentenceTransformer(MODEL)
    return _model


def _encode(texts: Sequence[str], prefix: str) -> NDArray[np.float32]:
    model = _load()
    out = model.encode(
        [prefix + t for t in texts],
        normalize_embeddings=True,
        batch_size=BATCH_SIZE,
        convert_to_numpy=True,
    )
    return np.asarray(out, dtype=np.float32)


def encode_queries(texts: Sequence[str]) -> NDArray[np.float32]:
    """Embed search queries (``"query: "`` prefix)."""
    return _encode(texts, "query: ")


def encode_passages(texts: Sequence[str]) -> NDArray[np.float32]:
    """Embed documents/passages (``"passage: "`` prefix)."""
    return _encode(texts, "passage: ")
