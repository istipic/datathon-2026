from __future__ import annotations

import pytest

from blizu_api.search import CategorySearch, keyword_scores, load_category_texts


@pytest.fixture(scope="module")
def keyword() -> CategorySearch:
    return CategorySearch(use_semantic=False)


def test_all_nine_categories_have_hr_texts() -> None:
    texts = load_category_texts()
    assert len(texts) == 9
    assert all(len(t.synonyms) >= 5 and len(t.description) > 40 for t in texts)


@pytest.mark.parametrize(
    ("query", "category"),
    [
        ("tabletke", "ljekarna"),
        ("apoteka", "ljekarna"),
        ("treba mi doktor", "lijecnik"),
        ("gdje se igra dijete", "park"),
        ("poslati paket", "posta"),
        ("kruh i mlijeko", "namirnice"),
        ("knjige za školu", "knjiznica"),
        ("tramvaj", "prijevoz"),
        ("dječji vrtić", "vrtic"),
        ("TRAMVAJ!!", "prijevoz"),
        ("Ljekarna", "ljekarna"),
    ],
)
def test_keyword_fallback_finds_the_right_category(
    keyword: CategorySearch, query: str, category: str
) -> None:
    result = keyword.search(query)
    assert result["method"] == "keyword"
    assert result["results"][0]["category"] == category


def test_keyword_matches_whole_words_not_substrings() -> None:
    # "mlijeko" contains the letters of the pharmacy synonym "lijek" but is not that word
    scores = keyword_scores("mlijeko", load_category_texts())
    assert scores["ljekarna"] < 0.5
    assert scores["namirnice"] == 1.0


def test_unrelated_query_returns_nothing(keyword: CategorySearch) -> None:
    assert keyword.search("xyzzy")["results"] == []
    assert keyword.search("a")["results"] == []


def test_at_most_three_results(keyword: CategorySearch) -> None:
    assert len(keyword.search("trgovina knjige lijekovi park pošta tramvaj")["results"]) <= 3


def test_falls_back_to_keywords_when_the_model_is_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import opendata_core.semantic as semantic

    def boom(_texts: list[str]) -> None:
        raise RuntimeError("model cannot be downloaded")

    monkeypatch.setattr(semantic, "encode_passages", boom)
    search = CategorySearch(use_semantic=True)
    result = search.search("tabletke")
    assert result["method"] == "keyword"
    assert result["results"][0]["category"] == "ljekarna"
    assert search.search("tabletke")["method"] == "keyword"  # failure is remembered, no retry storm


@pytest.mark.slow
def test_semantic_search_with_the_real_model() -> None:
    """Downloads/uses multilingual-e5-small. Run: uv run --package blizu-api --extra semantic pytest -m slow"""
    pytest.importorskip("sentence_transformers")
    search = CategorySearch()
    for query, category in [
        ("tabletke", "ljekarna"),
        ("treba mi doktor", "lijecnik"),
        ("poslati paket", "posta"),
        ("kruh i mlijeko", "namirnice"),
    ]:
        result = search.search(query)
        assert result["method"] == "semantic"
        assert result["results"][0]["category"] == category
    assert search.search("xyzzy")["results"] == []  # below the empirical floor
