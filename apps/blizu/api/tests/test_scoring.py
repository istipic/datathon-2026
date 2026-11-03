from __future__ import annotations

import pytest

from blizu_api import scoring as sc

CFG = sc.load_config()


def test_config_matches_the_spec() -> None:
    assert CFG.version == 1
    assert {p: (v.speed_mps, v.graph) for p, v in CFG.personas.items()} == {
        "opce": (1.33, "full"),
        "starija": (0.90, "full"),
        "roditelj": (1.10, "full"),
        "kolica": (0.90, "wheelchair"),
    }
    spec = {  # category: (good, max, opce, starija, roditelj, kolica)
        "lijecnik": (10, 30, 0.12, 0.22, 0.12, 0.12),
        "ljekarna": (10, 25, 0.10, 0.18, 0.08, 0.10),
        "vrtic": (10, 25, 0.08, 0.0, 0.22, 0.08),
        "skola": (15, 30, 0.08, 0.0, 0.15, 0.08),
        "knjiznica": (15, 40, 0.06, 0.07, 0.05, 0.06),
        "posta": (15, 35, 0.06, 0.10, 0.03, 0.06),
        "prijevoz": (5, 15, 0.20, 0.18, 0.12, 0.20),
        "park": (5, 15, 0.15, 0.10, 0.13, 0.15),
        "namirnice": (5, 15, 0.15, 0.15, 0.10, 0.15),
    }
    assert set(CFG.categories) == set(spec)
    for cid, (g, m, *w) in spec.items():
        c = CFG.categories[cid]
        assert (c.good_min, c.max_min) == (g, m)
        assert [c.weights[p] for p in ("opce", "starija", "roditelj", "kolica")] == w


@pytest.mark.parametrize("persona", ["opce", "starija", "roditelj", "kolica"])
def test_weights_sum_to_one_per_persona(persona: str) -> None:
    assert sum(c.weights[persona] for c in CFG.categories.values()) == pytest.approx(1.0)


def test_groups() -> None:
    groups = {cid: c.group for cid, c in CFG.categories.items()}
    assert groups["lijecnik"] == groups["ljekarna"] == "pop_65p"
    assert groups["vrtic"] == groups["skola"] == "pop_u15"
    assert {groups[c] for c in ("knjiznica", "posta", "prijevoz", "park", "namirnice")} == {
        "pop_total"
    }


def test_score_edges() -> None:
    assert sc.score(0, 10, 30) == 1.0
    assert sc.score(10, 10, 30) == 1.0  # t == g
    assert sc.score(30, 10, 30) == 0.0  # t == m
    assert sc.score(45, 10, 30) == 0.0
    assert sc.score(20, 10, 30) == pytest.approx(0.5)  # between
    assert sc.score(12, 10, 30) == pytest.approx(0.9)


def test_minutes() -> None:
    assert sc.minutes(798, 1.33) == pytest.approx(10.0)  # 798 m at 1.33 m/s
    assert sc.minutes(540, 0.9) == pytest.approx(10.0)
    assert sc.minutes(0, 1.1) == 0.0


def test_index_full_marks_and_rounding() -> None:
    assert sc.renormalised_index([(0.5, 1.0), (0.5, 1.0)]) == 100
    assert sc.renormalised_index([(0.5, 0.0), (0.5, 0.0)]) == 0
    assert sc.renormalised_index([(0.5, 1.0), (0.5, 0.0)]) == 50
    assert sc.renormalised_index([(1, 0.005)]) == 1  # 0.5 rounds up


def test_weights_are_renormalised_when_a_category_is_missing() -> None:
    # all categories with full score -> 100 even if only some have data
    full = [(c.weights["opce"], 1.0) for c in CFG.categories.values()]
    missing_one = full[1:]
    assert sc.renormalised_index(full) == 100
    assert sc.renormalised_index(missing_one) == 100
    # prijevoz (0.20) missing, others score 0.5 -> still 50 (not 40)
    items = [(c.weights["opce"], 0.5) for cid, c in CFG.categories.items() if cid != "prijevoz"]
    assert sc.renormalised_index(items) == 50


def test_zero_weight_categories_are_ignored() -> None:
    assert sc.renormalised_index([(0.0, 0.0), (0.2, 1.0)]) == 100
    assert sc.renormalised_index([(0.0, 1.0)]) is None
    assert sc.renormalised_index([]) is None


@pytest.mark.parametrize(
    ("index", "letter"),
    [
        (100, "A"),
        (85, "A"),
        (84, "B"),
        (70, "B"),
        (69, "C"),
        (55, "C"),
        (54, "D"),
        (40, "D"),
        (39, "E"),
        (0, "E"),
    ],
)
def test_grade_bands(index: int, letter: str) -> None:
    assert sc.grade(index, CFG.grades) == letter


@pytest.mark.parametrize(
    ("days", "factor"),
    [(0, 1.0), (365, 1.0), (366, 0.85), (1095, 0.85), (1100, 0.7), (4000, 0.7), (None, 0.7)],
)
def test_freshness_bands(days: float | None, factor: float) -> None:
    assert sc.freshness_factor(days, CFG.freshness) == factor


def test_category_confidence_and_labels() -> None:
    assert sc.category_confidence("official", 10, CFG) == 1.0
    assert sc.category_confidence("community", 10, CFG) == pytest.approx(0.8)
    assert sc.category_confidence("official", 600, CFG) == pytest.approx(0.85)
    assert sc.category_confidence("community", 2000, CFG) == pytest.approx(0.56)
    assert sc.category_confidence("unknown-tier", 10, CFG) == pytest.approx(
        0.8
    )  # treated as community
    labels = CFG.confidence_labels
    assert sc.confidence_label(0.85, labels) == "visoka"
    assert sc.confidence_label(0.8499, labels) == "srednja"
    assert sc.confidence_label(0.70, labels) == "srednja"
    assert sc.confidence_label(0.6999, labels) == "niska"


def test_overall_confidence_is_weighted_mean() -> None:
    assert sc.overall_confidence([(0.5, 1.0), (0.5, 0.7)]) == pytest.approx(0.85)
    assert sc.overall_confidence([(3, 1.0), (1, 0.6)]) == pytest.approx(0.9)
    assert sc.overall_confidence([(0, 1.0)]) is None


def test_parse_config_rejects_bad_input() -> None:
    raw = dict(CFG.raw)
    bad_cats = {k: dict(v) for k, v in raw["categories"].items()}  # type: ignore[union-attr]
    bad_cats["park"]["good_min"] = 20
    with pytest.raises(ValueError, match="good_min"):
        sc.parse_config({**raw, "categories": bad_cats})
    bad_cats = {k: dict(v) for k, v in raw["categories"].items()}  # type: ignore[union-attr]
    bad_cats["park"]["weights"] = {"opce": 1.0}
    with pytest.raises(ValueError, match="missing weights"):
        sc.parse_config({**raw, "categories": bad_cats})
