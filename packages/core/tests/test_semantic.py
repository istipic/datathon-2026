from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from opendata_core import semantic


class FakeModel:
    """Records calls; stands in for SentenceTransformer in unit tests only."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def encode(self, texts: list[str], **kwargs: Any) -> np.ndarray:
        self.calls.append({"texts": texts, **kwargs})
        return np.ones((len(texts), semantic.DIM), dtype=np.float64) / np.sqrt(semantic.DIM)


@pytest.fixture
def fake(monkeypatch: pytest.MonkeyPatch) -> FakeModel:
    model = FakeModel()
    monkeypatch.setattr(semantic, "_model", model)
    return model


def test_constants() -> None:
    assert semantic.MODEL == "intfloat/multilingual-e5-small"
    assert semantic.DIM == 384
    assert semantic.BATCH_SIZE == 64


def test_queries_get_query_prefix(fake: FakeModel) -> None:
    out = semantic.encode_queries(["ljekarna", "škola"])
    assert fake.calls[0]["texts"] == ["query: ljekarna", "query: škola"]
    assert fake.calls[0]["normalize_embeddings"] is True
    assert fake.calls[0]["batch_size"] == 64
    assert out.shape == (2, 384)
    assert out.dtype == np.float32


def test_passages_get_passage_prefix(fake: FakeModel) -> None:
    semantic.encode_passages(["apoteka, lijekovi"])
    assert fake.calls[0]["texts"] == ["passage: apoteka, lijekovi"]


def test_model_is_loaded_lazily_once(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(semantic, "_model", None)
    loaded: list[str] = []

    class Loader:
        def __init__(self, name: str) -> None:
            loaded.append(name)

        def encode(self, texts: list[str], **kwargs: Any) -> np.ndarray:
            return np.zeros((len(texts), semantic.DIM))

    import sys
    import types

    fake_mod = types.ModuleType("sentence_transformers")
    fake_mod.SentenceTransformer = Loader  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake_mod)
    assert loaded == []  # importing opendata_core.semantic loads nothing
    semantic.encode_queries(["a"])
    semantic.encode_passages(["b"])
    assert loaded == [semantic.MODEL]


@pytest.mark.slow
def test_real_model_ranks_pharmacy_closer_than_football_pitch() -> None:
    """Downloads multilingual-e5-small (~470 MB) on first run. Run: pytest -m slow."""
    pytest.importorskip("sentence_transformers")
    q = semantic.encode_queries(["ljekarna"])[0]
    p = semantic.encode_passages(["apoteka, lijekovi", "nogometno igralište"])
    sim_pharmacy = float(q @ p[0])
    sim_pitch = float(q @ p[1])
    assert q.shape == (384,)
    assert float(np.linalg.norm(q)) == pytest.approx(1.0, abs=1e-3)
    assert sim_pharmacy > sim_pitch
