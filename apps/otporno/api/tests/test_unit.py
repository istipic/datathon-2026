"""Unit tests: hot-day counting on the real Open-Meteo response, bands, priority, weights, flood level,
WMS capabilities, action rules, cooling geometry."""

from __future__ import annotations

from typing import Any

import numpy as np
import pytest

from otporno_api import actions, cooling, flood, flood_wms, heat, heat_calc, priority
from otporno_api.constants import BANDS, FLOOD_UNAVAILABLE, HV_LAYERS, MODELS
from otporno_api.om_client import estimate_cost, wait_needed


# ----------------------------------------------------------------------------- hot days (real response)
def _naive_count(daily: dict[str, Any], key: str, threshold: float, y0: int, y1: int) -> float:
    per_year: dict[int, list[float]] = {}
    for t, v in zip(daily["time"], daily[key], strict=True):
        y = int(t[:4])
        if y0 <= y <= y1 and v is not None:
            per_year.setdefault(y, []).append(v)
    counts = [
        sum(1 for v in vals if v >= threshold) for vals in per_year.values() if len(vals) >= 300
    ]
    return sum(counts) / len(counts)


def test_recorded_response_has_three_models_and_the_whole_period(
    om_response: dict[str, Any],
) -> None:
    daily = om_response["daily"]
    assert daily["time"][0] == "1991-01-01"
    assert daily["time"][-1] == "2050-12-31"
    for m in MODELS:
        assert f"temperature_2m_max_{m}" in daily
        assert f"temperature_2m_min_{m}" in daily


@pytest.mark.parametrize("model", MODELS)
def test_hot_days_and_tropical_nights_match_an_independent_count(
    om_response: dict[str, Any], model: str
) -> None:
    daily = om_response["daily"]
    got = heat_calc.model_metrics(daily, model)
    assert got["base_hot_days"] == pytest.approx(
        _naive_count(daily, f"temperature_2m_max_{model}", 30, 1991, 2020)
    )
    assert got["fut_hot_days"] == pytest.approx(
        _naive_count(daily, f"temperature_2m_max_{model}", 30, 2031, 2050)
    )
    assert got["base_trop_nights"] == pytest.approx(
        _naive_count(daily, f"temperature_2m_min_{model}", 20, 1991, 2020)
    )
    assert got["fut_trop_nights"] == pytest.approx(
        _naive_count(daily, f"temperature_2m_min_{model}", 20, 2031, 2050)
    )
    assert 0 < got["base_hot_days"] < 120


def test_ensemble_mean_min_max_and_future_is_not_cooler_than_today(
    om_response: dict[str, Any],
) -> None:
    per = heat_calc.all_models(om_response["daily"])
    assert set(per) == set(MODELS)
    mean, lo, hi = heat_calc.ensemble([v["fut_hot_days"] for v in per.values()]) or (0, 0, 0)
    assert lo <= mean <= hi
    base_mean = heat_calc.ensemble([v["base_hot_days"] for v in per.values()])[0]  # type: ignore[index]
    assert mean > base_mean


def test_incomplete_years_are_ignored() -> None:
    times = [f"2031-{m:02d}-{d:02d}" for m in (6, 7) for d in range(1, 29)]
    assert heat_calc.annual_counts(times, [31.0] * len(times), 30, 2031, 2031) == {}
    assert heat_calc.ensemble([None, None]) is None


# ----------------------------------------------------------------------------- bands and percentile
@pytest.mark.parametrize(
    ("score", "band"),
    [
        (0.0, "niska"),
        (0.2499, "niska"),
        (0.25, "umjerena"),
        (0.4999, "umjerena"),
        (0.5, "visoka"),
        (0.7999, "visoka"),
        (0.8, "vrlo visoka"),
        (1.0, "vrlo visoka"),
        (None, None),
    ],
)
def test_band_edges(score: float | None, band: str | None) -> None:
    assert heat.band_of(score) == band


def test_percentile_is_share_of_reference_at_or_below() -> None:
    ref = [1.0, 2.0, 3.0, 4.0]
    assert heat.percentile_of(3.0, ref) == 0.75
    assert heat.percentile_of(0.5, ref) == 0.0
    assert heat.percentile_of(9.0, ref) == 1.0
    assert heat.percentile_of(1.0, []) is None


def test_farthest_first_prefix_is_spread_out() -> None:
    pts = [(la / 4, lo / 4) for la in range(180, 190) for lo in range(56, 66)]
    order = heat.farthest_first(pts)
    assert sorted(order) == sorted(pts)
    first = order[:4]
    assert min(heat.km_between(a[0], a[1], b[0], b[1]) for a in first for b in first if a != b) > 25


# ----------------------------------------------------------------------------- flood
@pytest.mark.parametrize(
    ("flags", "level"),
    [
        ((True, True, True), 3),
        ((True, False, False), 3),
        ((False, True, True), 2),
        ((False, False, True), 1),
        ((False, False, False), 0),
    ],
)
def test_flood_level_from_flags(flags: tuple[bool, bool, bool], level: int) -> None:
    assert flood.flood_level(*flags) == level
    assert flood.flood_score(level) == {3: 1.0, 2: 0.66, 1: 0.33, 0: 0.0}[level]


def test_flood_cell_share_threshold() -> None:
    assert flood.level_from_cell_shares(0.10, 0.5, 0.9) == 3
    assert flood.level_from_cell_shares(0.09, 0.10, 0.9) == 2
    assert flood.level_from_cell_shares(0.0, 0.05, 0.10) == 1
    assert flood.level_from_cell_shares(0.0, 0.0, 0.09) == 0


def test_without_flags_flood_is_unknown_and_never_guessed() -> None:
    result = flood.assess()
    assert result.level is None
    assert result.message == FLOOD_UNAVAILABLE
    assert flood.assess({"high": True, "medium": None, "low": None}).level is None
    assert flood.assess({"high": False, "medium": True, "low": True}).level == 2


# ----------------------------------------------------------------------------- WMS capabilities
def test_wms_capabilities_parse(wms_capabilities: str) -> None:
    layers = flood_wms.parse_capabilities(wms_capabilities)
    by_name = {layer.name: layer for layer in layers}
    found = flood_wms.hazard_layers(layers)
    assert set(found) == set(HV_LAYERS)
    assert all(v is not None for v in found.values())
    assert found["high"].title.startswith("Opasnosti od poplava, velika vjerojatnost")  # type: ignore[union-attr]
    assert "poplave_opasnosti:hr.fd.vjerojatnost-pojavljivanja" in by_name
    bbox = found["high"].bbox  # type: ignore[union-attr]
    assert bbox is not None
    assert 13 < bbox[0] < bbox[2] < 20
    assert 42 < bbox[1] < bbox[3] < 47


def test_hazard_layers_are_not_queryable_so_the_ladder_stops_at_c(wms_capabilities: str) -> None:
    layers = flood_wms.parse_capabilities(wms_capabilities)
    assert not any(v.queryable for v in flood_wms.hazard_layers(layers).values() if v)
    assert flood_wms.ladder_step(layers) == "c"


# ----------------------------------------------------------------------------- priority and weights
def test_priority_formula() -> None:
    w = {"flood": 0.5, "heat": 0.35, "fire": 0.15}
    scores = {"flood": 1.0, "heat": 0.5, "fire": 0.0}
    # pop 100, 65+ = 40: exposure = 40 + 0.5 * 60 = 70; risk = 0.5 + 0.175 + 0 = 0.675
    assert priority.cell_priority(scores, w, 100, 40) == pytest.approx(0.675 * 70)


def test_missing_hazards_are_renormalised() -> None:
    w = priority.default_weights()
    eff = priority.effective_weights(w, {"flood": False, "heat": True, "fire": False})
    assert eff == {"flood": 0.0, "heat": 1.0, "fire": 0.0}
    assert priority.cell_priority(
        {"flood": None, "heat": 0.8, "fire": None}, w, 10, 10
    ) == pytest.approx(0.8 * 10)
    assert priority.cell_priority({"flood": None, "heat": None, "fire": None}, w, 10, 10) == 0.0


def test_weight_validation() -> None:
    assert priority.validate_weights({"flood": 0.5, "heat": 0.35, "fire": 0.15})["heat"] == 0.35
    assert priority.validate_weights(
        {"flood": 0.5, "heat": 0.5, "fire": 0.005}
    )  # sum 1.005 is inside 1 +- 0.01
    for bad in (
        {"flood": 0.5, "heat": 0.5, "fire": 0.1},
        {"flood": 0.2, "heat": 0.2, "fire": 0.2},
        {"flood": -0.1, "heat": 0.6, "fire": 0.5},
    ):
        with pytest.raises(priority.WeightError):
            priority.validate_weights(bad)


def test_exposure_weight_clamps_65p_to_total() -> None:
    assert priority.exposure_weight(10, 20) == 10
    assert priority.exposure_weight(None, None) == 0


# ----------------------------------------------------------------------------- quota arithmetic
def test_cost_model_matches_the_measured_header() -> None:
    assert estimate_cost(6, 21915) == pytest.approx(
        939.2, abs=0.1
    )  # x-ratelimit-cost measured 2026-11-04


def test_wait_needed_rolling_window() -> None:
    calls = [(0.0, 400.0), (30.0, 150.0)]
    assert wait_needed(calls, now=40.0, window=60.0, limit=570, cost=20) == 0.0
    assert wait_needed(calls, now=40.0, window=60.0, limit=570, cost=100) == pytest.approx(
        20.0
    )  # first call leaves at t=60
    assert (
        wait_needed([], now=0.0, window=60.0, limit=570, cost=939.2) == 0.0
    )  # larger than the limit, empty window
    assert wait_needed([(0.0, 10.0)], now=1.0, window=60.0, limit=570, cost=939.2) == pytest.approx(
        59.0
    )


# ----------------------------------------------------------------------------- action rules
def test_action_rules_file_is_valid_and_every_rule_cites_an_https_source() -> None:
    doc = actions.load_document()
    assert len(doc["actions"]) >= 36
    groups: dict[tuple[str, str], int] = {}
    for a in doc["actions"]:
        src = doc["sources"][a["source"]]
        assert src["url"].startswith("https://")
        assert src["retrieved"] == "2026-11-04"
        groups[(a["hazard"], a["audience"])] = groups.get((a["hazard"], a["audience"]), 0) + 1
    for hazard in ("flood", "heat"):
        for audience in actions.AUDIENCES:
            assert groups[(hazard, audience)] >= 4, (hazard, audience)
    assert {a["min_band"] for a in doc["actions"]} <= set(BANDS)


def test_action_rule_errors_are_reported(tmp_path: Any) -> None:
    bad = tmp_path / "r.yaml"
    bad.write_text(
        "sources: [{id: s, title: t, url: 'http://x', retrieved: '2026-11-04'}]\nactions: [{id: a}]\n",
        encoding="utf-8",
    )
    with pytest.raises(actions.RuleError):
        actions.load_document(bad)


# ----------------------------------------------------------------------------- cooling geometry
def test_lattice_has_sixteen_points_in_a_one_km_cell() -> None:
    lat = cooling.lattice_in_cell(0, 0, 1000, 1000)
    assert lat.shape == (16, 2)
    assert lat[:, 0].min() == pytest.approx(125)
    assert lat[:, 0].max() == pytest.approx(875)


def test_greedy_choice_covers_at_least_as_much_as_before() -> None:
    demand_xy = np.array([[0.0, 0], [100, 0], [3000, 0], [3100, 0], [6000, 0]])
    demand = np.array([5.0, 5.0, 4.0, 4.0, 1.0])
    sites = [
        {"id": i, "name": f"s{i}", "kind": "school", "lon": 15.5, "lat": 45.5} for i in range(3)
    ]
    sites_xy = np.array([[50.0, 0], [3050, 0], [6000, 0]])
    problem = cooling.CoolingProblem(demand_xy, demand, sites_xy, sites)
    res1 = cooling.propose(problem, 1)
    res2 = cooling.propose(problem, 2)
    assert res1["covered_after"] >= res1["covered_before"] == 0
    assert res1["covered_after"] == 10
    assert res2["covered_after"] == 18
    mask = np.array([True, True, False, False, False])
    res3 = cooling.propose(problem, 1, covered_before_mask=mask)
    assert res3["covered_before"] == 10
    assert res3["covered_after"] == 18
