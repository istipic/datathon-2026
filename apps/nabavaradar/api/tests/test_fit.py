"""Fit formula, components S/C/G/T, edge cases and the competition flag."""

from __future__ import annotations

import pytest

from nabavaradar_api.fit import (
    Components,
    crosswalk_component,
    days_to_deadline,
    geography_component,
    rank_divisions,
    rescale_similarity,
    time_component,
)
from nabavaradar_api.ingest.stats import competition_flag


def test_weights_are_55_25_10_10() -> None:
    assert Components(1, 1, 1, 1).fit() == pytest.approx(1.0)
    assert Components(1, 0, 0, 0).fit() == pytest.approx(0.55)
    assert Components(0, 1, 0, 0).fit() == pytest.approx(0.25)
    assert Components(0, 0, 1, 0).fit() == pytest.approx(0.10)
    assert Components(0, 0, 0, 1).fit() == pytest.approx(0.10)
    assert Components(0.5, 1.0, 0.2, 0.0).fit() == pytest.approx(0.275 + 0.25 + 0.02)


@pytest.mark.parametrize(
    ("cosine", "expected"),
    [(0.70, 0.0), (0.80, 0.5), (0.90, 1.0), (0.95, 1.0), (0.60, 0.0), (0.75, 0.25)],
)
def test_s_rescales_between_the_5th_and_95th_percentile(cosine: float, expected: float) -> None:
    assert rescale_similarity(cosine, 0.70, 0.90) == pytest.approx(expected)


def test_s_degenerate_percentiles_give_zero() -> None:
    assert rescale_similarity(0.8, 0.9, 0.9) == 0.0
    assert rescale_similarity(0.8, 0.95, 0.9) == 0.0


@pytest.mark.parametrize(
    ("position", "expected"),
    [(0, 1.0), (1, 1.0), (2, 1.0), (3, 0.5), (9, 0.5), (10, 0.0), (25, 0.0)],
)
def test_c_top3_top10_else_zero(position: int, expected: float) -> None:
    ranked = [f"{i:02d}" for i in range(30)]
    assert crosswalk_component(ranked[position], ranked) == expected


def test_c_division_not_in_ranking_or_missing() -> None:
    assert crosswalk_component("99", ["01", "02"]) == 0.0
    assert crosswalk_component(None, ["01"]) == 0.0
    assert crosswalk_component("01", []) == 0.0


def test_rank_divisions_uses_max_similarity_over_activities() -> None:
    ranked = rank_divisions([{"45": 0.80, "71": 0.70}, {"71": 0.85, "33": 0.60}])
    assert ranked == ["71", "45", "33"]
    assert rank_divisions([]) == []


@pytest.mark.parametrize(
    ("buyer", "company", "expected"),
    [
        ("HR035", "HR035", 1.0),  # same NUTS3
        ("HR035", "HR034", 0.5),  # same NUTS2 (HR03), other county
        ("HR035", "HR050", 0.2),  # different NUTS2
        ("HR065", "HR050", 0.2),  # Zagrebačka vs Grad Zagreb are different NUTS2 (HR06 / HR05)
        ("HR021", "HR028", 0.5),  # both Panonska Hrvatska (HR02)
        (None, "HR035", 0.5),  # unknown buyer
        ("HR035", None, 0.5),  # unknown company county
        (None, None, 0.5),
        ("HRV", "HR035", 0.5),  # a country code is not a NUTS3
    ],
)
def test_g_mapping(buyer: str | None, company: str | None, expected: float) -> None:
    assert geography_component(buyer, company) == expected


@pytest.mark.parametrize(
    ("days", "expected"),
    [
        (30.0, 1.0),
        (15.0, 1.0),  # >= 15 days is full
        (14.999, pytest.approx((14.999 - 3) / 12)),
        (9.0, 0.5),  # linear: midpoint of 3..15
        (3.001, pytest.approx(0.001 / 12)),
        (3.0, 0.0),  # zero at 3 days
        (1.0, 0.0),
        (0.0, 0.0),  # deadline is now: not expired yet, T = 0
    ],
)
def test_t_edges(days: float, expected: float) -> None:
    assert time_component(days) == expected


def test_t_expired_is_excluded_and_unknown_deadline_is_neutral() -> None:
    assert time_component(-0.0001) is None
    assert time_component(-5) is None
    assert time_component(None) == 0.5


def test_days_to_deadline() -> None:
    from datetime import UTC, datetime

    now = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)
    assert days_to_deadline(datetime(2026, 11, 19, 12, 0, tzinfo=UTC), now) == pytest.approx(15.0)
    assert days_to_deadline(datetime(2026, 11, 4, 0, 0, tzinfo=UTC), now) == pytest.approx(-0.5)
    assert days_to_deadline(None, now) is None


@pytest.mark.parametrize(
    ("n", "share", "expected"),
    [
        (10, 0.40, True),  # both thresholds are inclusive
        (10, 0.3999, False),
        (9, 0.90, False),  # too few awards: no flag
        (250, 0.40, True),
        (250, 0.0, False),
        (0, None, False),
        (None, 0.5, False),
        (30, None, False),
    ],
)
def test_single_bid_flag_thresholds(n: int | None, share: float | None, expected: bool) -> None:
    assert competition_flag(n, share) is expected


# ---------------------------------------------------------------------------- config (config/fit.yaml)
def test_shipped_config_loads_and_weights_sum_to_one() -> None:
    from nabavaradar_api.fit import load_fit_config

    cfg = load_fit_config()
    assert sum(cfg.weights.values()) == pytest.approx(1.0)
    assert set(cfg.weights) == {"S", "C", "G", "T"}
    assert 0 < cfg.secondary_activity_discount <= 1
    assert 0 <= cfg.c_group_bonus <= 1


@pytest.mark.parametrize(
    "bad",
    [
        {"weights": {"S": 0.5, "C": 0.5, "G": 0.5, "T": 0.5}},
        {"weights": {"S": 1.0}},
        {"secondary_activity_discount": 0},
        {"secondary_activity_discount": 1.5},
        {"c_group_bonus": -0.1},
        {"typo_key": 1},
    ],
)
def test_bad_fit_config_is_rejected(bad: dict) -> None:
    from nabavaradar_api.fit import parse_fit_config

    with pytest.raises(ValueError, match="fit config|weights|discount"):
        parse_fit_config(bad)


def test_group_bonus_only_for_the_companys_best_groups() -> None:
    from nabavaradar_api.fit import FitConfig, group_component

    cfg = FitConfig(c_group_bonus=0.25, c_group_top=2)
    assert group_component("451", ["451", "452", "453"], cfg) == 0.25
    assert group_component("453", ["451", "452", "453"], cfg) == 0.0  # outside the top 2
    assert group_component(None, ["451"], cfg) == 0.0
    assert group_component("451", ["451"], FitConfig(c_group_bonus=0.0)) == 0.0


def test_components_fit_accepts_explicit_weights() -> None:
    w = {"S": 1.0, "C": 0.0, "G": 0.0, "T": 0.0}
    assert Components(0.4, 1, 1, 1).fit(w) == pytest.approx(0.4)


# ---------------------------------------------------------------------------- lots / procedures
def _item(pub_no: str, fit: float, procedure_id: str | None, title: str, pub: str = "2026-10-20"):
    return {
        "pub_no": pub_no,
        "fit": fit,
        "procedure_id": procedure_id,
        "title": title,
        "buyer": "GRAD ZAGREB",
        "pub_date": pub,
        "deadline": "2026-11-20T09:00:00+01:00",
        "url_html": f"https://ted.europa.eu/{pub_no}",
    }


def test_notices_of_one_procedure_collapse_to_the_best_one() -> None:
    from nabavaradar_api.match import collapse_procedures

    items = [
        _item("2-1", 0.9, "P1", "Obnova škole"),
        _item("3-1", 0.8, "P2", "Nabava mlijeka"),
        _item("4-1", 0.7, "P1", "Obnova škole", pub="2026-10-25"),
    ]
    out = collapse_procedures(items)
    assert [i["pub_no"] for i in out] == ["2-1", "3-1"]
    assert out[0]["group"]["size"] == 2
    assert out[0]["group"]["others"][0]["pub_no"] == "4-1"
    assert out[1]["group"] == {"size": 1, "others": []}


def test_newest_publication_wins_a_tie_within_a_procedure() -> None:
    from nabavaradar_api.match import collapse_procedures

    out = collapse_procedures(
        [
            _item("2-1", 0.9, "P1", "Obnova škole", pub="2026-10-20"),
            _item("4-1", 0.9, "P1", "Obnova škole", pub="2026-10-25"),
        ]
    )
    assert len(out) == 1
    assert out[0]["pub_no"] == "4-1"
    assert [o["pub_no"] for o in out[0]["group"]["others"]] == ["2-1"]


def test_lots_without_procedure_id_group_by_buyer_and_base_title() -> None:
    from nabavaradar_api.match import procedure_key

    a = _item("1-1", 0.5, None, "Nabava vozila - grupa 1")
    b = _item("2-1", 0.5, None, "Nabava vozila - grupa 2")
    c = _item("3-1", 0.5, None, "Nabava računala")
    assert procedure_key(a) == procedure_key(b)
    assert procedure_key(a) != procedure_key(c)
    assert procedure_key({**a, "buyer": "DRUGI"}) != procedure_key(a)


def test_explanation_lists_the_signals_in_plain_croatian() -> None:
    from nabavaradar_api.subscriptions import explain_item

    reasons = explain_item(
        {
            "components": {"S": 0.92, "C": 1.0, "G": 1.0, "T": 1.0},
            "best_activity": {"label": "Proizvodnja kruha"},
            "cpv_division_label": "Prehrambeni proizvodi",
            "county": "Splitsko-dalmatinska županija",
            "days_left": 12.4,
            "signals": {"cpv_group_match": True},
        }
    )
    text = " ".join(reasons)
    assert "Proizvodnja kruha" in text
    assert "92 %" in text
    assert "Prehrambeni proizvodi" in text
    assert "uža CPV skupina" in text
    assert "vašoj županiji" in text
    assert "12 dana" in text
