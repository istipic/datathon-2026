"""Service, planner and HTTP API on REAL data: the 1 km OSM subgraph around Trg bana Jelacica,
the real facilities/cells/source metadata of the same area (recorded 2026-11-03)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import respx
from conftest import TRG, build_store
from fastapi.testclient import TestClient

from blizu_api import service
from blizu_api.constants import CATEGORIES
from blizu_api.ingest.graph import GraphData
from blizu_api.planner import Planner
from blizu_api.scoring import minutes, renormalised_index
from blizu_api.store import DataStore, check_access_consistency

LAT, LON = TRG
SPEED = {"opce": 1.33, "starija": 0.90, "roditelj": 1.10, "kolica": 0.90}
NOMINATIM_FIXTURE = (
    Path(__file__).parents[4]
    / "packages"
    / "core"
    / "tests"
    / "fixtures"
    / "nominatim"
    / "2026-11-03_search_trg_bana_jelacica.json"
)


# ---------------------------------------------------------------------------------- /access logic
def test_access_returns_nine_categories_with_data_at_the_central_square(store: DataStore) -> None:
    result = service.compute_access(store, LAT, LON, "opce")
    assert [c["category"] for c in result["categories"]] == list(CATEGORIES)
    assert all(c["has_data"] for c in result["categories"])
    assert all(c["minutes"] is not None for c in result["categories"])
    assert result["grade"] in set("ABCDE")
    assert 0 <= result["index"] <= 100
    assert result["snapped_distance_m"] < 100
    assert result["confidence"]["label"] in {"visoka", "srednja", "niska"}
    # the centre of Zagreb is well served: every category within its "good" threshold
    for c in result["categories"]:
        assert c["minutes"] <= c["good_min"], (c["category"], c["minutes"])
    assert result["index"] == 100


def test_minutes_scale_with_persona_speed_and_wheelchair_graph(store: DataStore) -> None:
    opce = service.compute_access(store, LAT, LON, "opce")
    starija = service.compute_access(store, LAT, LON, "starija")
    roditelj = service.compute_access(store, LAT, LON, "roditelj")
    kolica = service.compute_access(store, LAT, LON, "kolica")
    rows = zip(
        opce["categories"],
        starija["categories"],
        roditelj["categories"],
        kolica["categories"],
        strict=True,
    )
    detours = 0
    for a, s, r, k in rows:
        assert s["minutes"] > a["minutes"], a["category"]  # slower walker, same graph
        assert s["minutes"] == pytest.approx(a["minutes"] * 1.33 / 0.90, abs=0.15)
        assert r["minutes"] == pytest.approx(a["minutes"] * 1.33 / 1.10, abs=0.15)
        assert k["minutes"] >= s["minutes"] - 0.05, a["category"]  # fewer edges for wheelchairs
        detours += k["minutes"] > s["minutes"] + 0.5
    assert detours >= 1, "the real box has hundreds of steps: some category needs a detour"
    assert any("invalidska kolica" in w for w in kolica["warnings"])


def test_index_is_the_renormalised_weighted_score(store: DataStore) -> None:
    for persona in ("opce", "starija", "kolica"):
        result = service.compute_access(store, 45.8160, 15.9650, persona)
        items = [(c["weight"], c["score"]) for c in result["categories"]]
        assert result["index"] == renormalised_index(items)


def test_zero_weight_categories_do_not_enter_the_index(store: DataStore) -> None:
    result = service.compute_access(store, LAT, LON, "starija")
    zero = {c["category"] for c in result["categories"] if c["weight"] == 0}
    assert zero == {"vrtic", "skola"}  # not relevant for the "starija" persona
    assert all(c["minutes"] is not None for c in result["categories"])  # still shown


def test_minutes_follow_distance_and_speed(store: DataStore) -> None:
    result = service.compute_access(store, LAT, LON, "roditelj")
    for c in result["categories"]:
        assert c["minutes"] == pytest.approx(minutes(c["distance_m"], SPEED["roditelj"]), abs=0.06)


def test_nearest_facility_is_real_and_has_source_and_tier(store: DataStore) -> None:
    result = service.compute_access(store, LAT, LON, "opce")
    by_cat = {c["category"]: c for c in result["categories"]}
    assert by_cat["prijevoz"]["tier"] == "official"
    assert by_cat["prijevoz"]["nearest"]["source_id"] == "zet-gtfs"
    assert by_cat["ljekarna"]["tier"] == "community"
    assert by_cat["ljekarna"]["nearest"]["source_id"] == "osm-zagreb"
    assert by_cat["vrtic"]["nearest"]["source_id"] == "zg-vrtici"
    assert by_cat["vrtic"]["freshness_days"] > 1000  # the register is from 2022
    assert any("Dječji vrtić" in w and "godina" in w for w in result["warnings"])
    for c in result["categories"]:
        assert c["nearest"]["name"]
        assert 45.7 < c["nearest"]["lat"] < 45.9
        assert 15.9 < c["nearest"]["lon"] < 16.1


def test_missing_category_is_flagged_and_weights_renormalised(
    subgraph: GraphData, store: DataStore
) -> None:
    without_park = build_store(subgraph, drop_category="park")
    full = service.compute_access(store, LAT, LON, "opce")
    reduced = service.compute_access(without_park, LAT, LON, "opce")
    park = next(c for c in reduced["categories"] if c["category"] == "park")
    assert park["has_data"] is False
    assert park["minutes"] is None
    assert any("Park" in w and "nema učitanih podataka" in w for w in reduced["warnings"])
    # everything else scored 1.0 at the centre -> renormalised index stays 100 (not 85)
    assert full["index"] == reduced["index"] == 100


def test_address_far_from_the_network_is_rejected(store: DataStore) -> None:
    with pytest.raises(service.FarFromNetworkError) as err:
        service.compute_access(store, LAT, LON + 0.04, "opce")  # ~3 km east of the 1 km subgraph
    assert err.value.snapped_m > 300


def test_compare_gives_signed_differences(store: DataStore) -> None:
    cmp = service.compare(store, (LAT, LON), (45.8100, 15.9800), "opce")
    assert len(cmp["differences"]) == 9
    ra, rb = cmp["a"], cmp["b"]
    for d, ca, cb in zip(cmp["differences"], ra["categories"], rb["categories"], strict=True):
        assert d["minutes_diff"] == pytest.approx(round(cb["minutes"] - ca["minutes"], 1))
    assert cmp["index_diff"] == rb["index"] - ra["index"]


# ---------------------------------------------------------------------------------- planner
@pytest.fixture(scope="module")
def planner(store: DataStore) -> Planner:
    return Planner(store)


def test_need_summary_and_features(planner: Planner, store: DataStore) -> None:
    need = planner.need("vrtic", "roditelj")
    s = need["summary"]
    assert len(need["features"]) == len(store.cells)
    assert s["pop_group_label"] == "djeca do 15 godina"
    assert s["good_min"] == 10
    assert s["max_min"] == 25
    assert 0 <= s["share_within_g"] <= 1
    assert s["pop_group_total"] == round(store.cells["pop_u15"].fillna(0).sum())
    assert all(f["properties"]["unmet"] >= 0 for f in need["features"])
    assert all(f["geometry"]["type"] == "Polygon" for f in need["features"])


def test_need_uses_total_population_when_age_groups_are_missing(subgraph: GraphData) -> None:
    store = build_store(subgraph)
    store.has_age_groups = False
    need = Planner(store).need("lijecnik", "starija")
    assert need["summary"]["pop_group_label"] == "ukupno stanovništvo"
    assert need["summary"]["has_age_groups"] is False
    assert need["summary"]["pop_group_total"] == round(store.cells["pop_total"].fillna(0).sum())


@pytest.mark.parametrize("category", ["vrtic", "ljekarna", "park"])
@pytest.mark.parametrize("persona", ["opce", "kolica"])
def test_optimise_returns_sites_and_never_reduces_coverage(
    planner: Planner, category: str, persona: str
) -> None:
    for k in (1, 3):
        result = planner.optimise(category, persona, k)
        assert len(result["sites"]) <= k
        assert result["share_after"] >= result["share_before"]
        assert 0 <= result["share_before"] <= 1
        assert result["share_after"] <= 1.0 + 1e-9
        total = sum(s["newly_covered"] for s in result["sites"])
        assert abs(result["total_newly_covered"] - total) <= len(result["sites"])  # rounding only
        for s in result["sites"]:
            assert 45.80 < s["lat"] < 45.83
            assert 15.96 < s["lon"] < 16.0  # inside the real subgraph
            assert s["newly_covered"] >= 0


def test_more_sites_never_cover_fewer_people(planner: Planner) -> None:
    r1 = planner.optimise("vrtic", "roditelj", 1)
    r3 = planner.optimise("vrtic", "roditelj", 3)
    assert r3["share_after"] >= r1["share_after"] - 1e-12
    assert r3["sites"][0] == r1["sites"][0]  # greedy: the first pick does not depend on k


def test_optimise_is_deterministic(planner: Planner) -> None:
    assert planner.optimise("ljekarna", "opce", 2) == planner.optimise("ljekarna", "opce", 2)


def test_need_and_optimise_share_the_same_definition(planner: Planner) -> None:
    need = planner.need("vrtic", "roditelj")["summary"]["share_within_g"]
    before = planner.optimise("vrtic", "roditelj", 1)["share_before"]
    assert need == pytest.approx(before)


# ---------------------------------------------------------------------------------- HTTP API
# (the `client_factory` and `client` fixtures live in conftest.py)
def test_api_access_contract(client: TestClient) -> None:
    r = client.get("/api/v1/access", params={"lat": LAT, "lon": LON, "persona": "opce"})
    assert r.status_code == 200
    body = r.json()
    expected = {"index", "grade", "confidence", "persona", "snapped_distance_m", "categories"}
    assert set(body) >= expected | {"warnings", "computed_at"}
    assert len(body["categories"]) == 9
    first = body["categories"][0]
    assert set(first) >= {"category", "label", "minutes", "score", "weight", "nearest", "tier"}
    assert set(first) >= {"freshness_days"}
    assert set(first["nearest"]) >= {"name", "address", "lon", "lat", "source_id"}


def test_api_access_validation_and_422s(client: TestClient) -> None:
    ok = {"lat": LAT, "lon": LON, "persona": "opce"}
    for bad in ({"lat": 48.85, "lon": 2.35}, {"persona": "robot"}, {"lat": "abc"}, {"lon": 99}):
        r = client.get("/api/v1/access", params={**ok, **bad})
        assert r.status_code == 422
        assert r.headers["content-type"].startswith("application/problem+json")
    far = client.get("/api/v1/access", params={**ok, "lon": LON + 0.04})
    assert far.status_code == 422
    assert "daleko od pješačke mreže" in far.json()["detail"]


def test_api_compare_facilities_scoring(client: TestClient) -> None:
    params = {"a": f"{LAT},{LON}", "b": "45.8100,15.9800", "persona": "starija"}
    cmp = client.get("/api/v1/compare", params=params)
    assert cmp.status_code == 200
    assert len(cmp.json()["differences"]) == 9
    assert client.get("/api/v1/compare", params={**params, "a": "x"}).status_code == 422
    fac = client.get(
        "/api/v1/facilities", params={"bbox": "15.96,45.80,15.99,45.82", "category": "park"}
    )
    assert fac.status_code == 200
    body = fac.json()
    assert body["type"] == "FeatureCollection"
    assert body["features"]
    assert all(f["properties"]["category"] == "park" for f in body["features"])
    assert all(15.96 <= f["geometry"]["coordinates"][0] <= 15.99 for f in body["features"])
    assert client.get("/api/v1/facilities", params={"bbox": "1,2,3"}).status_code == 422
    cfg = client.get("/api/v1/scoring").json()
    assert cfg["version"] == 1
    assert cfg["categories"]["lijecnik"]["weights"]["starija"] == 0.22


def test_api_plan_endpoints(client: TestClient) -> None:
    need = client.get("/api/v1/plan/need", params={"category": "vrtic", "persona": "roditelj"})
    assert need.status_code == 200
    assert need.json()["summary"]["pop_group_label"] == "djeca do 15 godina"
    payload = {"category": "vrtic", "persona": "roditelj", "k": 3}
    opt = client.post("/api/v1/plan/optimise", json=payload)
    assert opt.status_code == 200
    body = opt.json()
    assert len(body["sites"]) <= 3
    assert body["share_after"] >= body["share_before"]
    for bad in ({"k": 0}, {"k": 6}, {"extra": 1}, {"category": "zzz"}):
        response = client.post("/api/v1/plan/optimise", json={**payload, "k": 2, **bad})
        assert response.status_code == 422


def test_api_search_and_geocode_with_recorded_nominatim(client: TestClient) -> None:
    s = client.get("/api/v1/search", params={"q": "apoteka"})
    assert s.status_code == 200
    assert s.json()["results"][0]["category"] == "ljekarna"
    assert s.json()["results"][0]["label"] == "Ljekarna"
    assert client.get("/api/v1/search", params={"q": "x" * 121}).status_code == 422
    real = json.loads(NOMINATIM_FIXTURE.read_text(encoding="utf-8"))
    with respx.mock:
        route = respx.get("https://nominatim.openstreetmap.org/search").respond(200, json=real)
        g = client.get("/api/v1/geocode", params={"q": "Trg bana Jelačića, Zagreb"})
        assert g.status_code == 200
        body = g.json()
        assert body["results"][0]["lat"] == pytest.approx(45.8130887)
        assert body["results"][0]["title"] == "Trg bana Josipa Jelačića"
        assert body["attribution"] == "© OpenStreetMap contributors (Nominatim)"
        sent = dict(route.calls.last.request.url.params)
        assert sent["viewbox"] == "15.75,45.7,16.25,45.95"
        assert sent["bounded"] == "1"
        assert sent["countrycodes"] == "hr"
    assert client.get("/api/v1/geocode", params={"q": "ab"}).status_code == 422


def test_api_free_places_without_data_is_a_clear_503(client: TestClient) -> None:
    r = client.get("/api/v1/kindergartens/free-places")
    assert r.status_code == 503
    assert "slobodnim mjestima" in r.json()["detail"]


def test_stale_access_arrays_are_detected(store: DataStore) -> None:
    ids = {int(i) for i in store.facilities.index}
    check_access_consistency(store.arrays, ids)  # consistent
    with pytest.raises(RuntimeError, match="ingest access"):
        check_access_consistency(store.arrays, set(list(ids)[:5]))


def test_api_starts_without_data_and_answers_503(client_factory) -> None:  # type: ignore[no-untyped-def]
    def broken_loader() -> DataStore:
        raise RuntimeError("manifest has no 'graph'; run `blizu ingest` first")

    with client_factory(broken_loader) as c:
        assert c.get("/health").status_code == 200  # the container stays up
        for url in (
            "/api/v1/access?lat=45.81&lon=15.97&persona=opce",
            "/api/v1/scoring",
            "/api/v1/plan/need?category=vrtic&persona=opce",
        ):
            r = c.get(url)
            assert r.status_code == 503, url
            assert r.headers["content-type"].startswith("application/problem+json")
            assert "učitavaju" in r.json()["detail"]
        assert (
            c.post(
                "/api/v1/plan/optimise", json={"category": "vrtic", "persona": "opce", "k": 1}
            ).status_code
            == 503
        )


def test_responses_never_contain_nan_for_unnamed_or_address_less_facilities(
    store: DataStore, client: TestClient
) -> None:
    """pandas turns missing text into NaN; it must never reach the API ("NaN · NaN" in the UI)."""
    import math

    import numpy as np

    rng = np.random.default_rng(11)
    g = store.graph
    sample = rng.choice(g.n_nodes, size=40, replace=False)
    unnamed_seen = 0
    for i in sample:
        for persona in ("opce", "kolica"):
            result = service.compute_access(store, float(g.lat[i]), float(g.lon[i]), persona)
            json.dumps(result, allow_nan=False)  # raises ValueError on NaN
            for c in result["categories"]:
                near = c["nearest"]
                if near:
                    assert isinstance(near["name"], str)
                    assert near["address"] is None or isinstance(near["address"], str)
                    assert not (isinstance(near["address"], float) and math.isnan(near["address"]))
                    unnamed_seen += near["address"] is None
    assert unnamed_seen > 0, "the real data has facilities without an address (e.g. parks)"
    r = client.get("/api/v1/facilities", params={"bbox": "15.96,45.80,15.99,45.82"})
    assert "NaN" not in r.text
    assert any(f["properties"]["address"] is None for f in r.json()["features"])
