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
