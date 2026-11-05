"""``/isochrone``, ``/route`` and the per-cell part of ``/plan/optimise`` on REAL data.

Everything runs on the recorded 1 km OSM subgraph around Trg bana Jelacica (3403 nodes, 8960
edges, 2026-11-03) with the real facilities and cells; the expectations are recomputed
independently (plain Dijkstra over the whole graph) or taken from ``/access``.
"""

from __future__ import annotations

import json
import math
import time
from collections.abc import Iterator

import numpy as np
import pytest
from conftest import TRG
from fastapi.testclient import TestClient
from scipy.sparse.csgraph import dijkstra
from shapely.geometry import Polygon
from shapely.prepared import prep

from blizu_api import service
from blizu_api.constants import CATEGORIES
from blizu_api.isochrone import BUCKET_MIN, compute_isochrone
from blizu_api.planner import Planner
from blizu_api.route import compute_route
from blizu_api.store import DataStore
from blizu_api.walk import (
    InvalidRequestError,
    LruCache,
    NotReachableError,
    WalkIndex,
    resolve_origin,
)
from blizu_api.walk_service import WalkService

LAT, LON = TRG
PERSONAS = ("opce", "starija", "roditelj", "kolica")
OTHER_ORIGINS = [(45.8160, 15.9650), (45.8100, 15.9800), (45.8090, 15.9710)]
ORIGINS = [(LAT, LON), *OTHER_ORIGINS]


@pytest.fixture(scope="module")
def walk(store: DataStore) -> WalkService:
    return WalkService(store)


@pytest.fixture(scope="module")
def planner(store: DataStore) -> Planner:
    return Planner(store)


def iso(walk: WalkService, lat: float, lon: float, persona: str, max_min: int = 15) -> dict:
    return json.loads(walk.isochrone(lat, lon, persona, max_min))


def segments(payload: dict) -> list[tuple[float, tuple[float, float], tuple[float, float]]]:
    """(t, a, b) for every drawn segment."""
    out = []
    for feature in payload["buckets"]["features"]:
        for a, b in feature["geometry"]["coordinates"]:
            out.append((feature["properties"]["t"], tuple(a), tuple(b)))
    return out


def key5(store: DataStore, i: int) -> tuple[float, float]:
    """(lon, lat) of node ``i`` rounded to 5 decimals the way the API does (numpy rounding)."""
    return float(np.round(store.graph.lon[i], 5)), float(np.round(store.graph.lat[i], 5))


def coord_node(store: DataStore) -> dict[tuple[float, float], int]:
    g = store.graph
    return {
        (float(lo), float(la)): i
        for i, (lo, la) in enumerate(zip(np.round(g.lon, 5), np.round(g.lat, 5), strict=True))
    }


# ----------------------------------------------------------------------------- isochrone: shape
@pytest.mark.parametrize("persona", PERSONAS)
def test_isochrone_contract_and_bucket_budget(walk: WalkService, persona: str) -> None:
    p = iso(walk, LAT, LON, persona, 20)
    assert set(p) == {
        "origin",
        "persona",
        "speed_mps",
        "max_min",
        "bucket_min",
        "buckets",
        "facilities",
        "counts",
    }
    assert p["persona"] == persona
    assert p["max_min"] == 20
    assert p["bucket_min"] == BUCKET_MIN
    assert set(p["origin"]) == {"lon", "lat", "snapped_m"}
    assert p["buckets"]["type"] == "FeatureCollection"
    features = p["buckets"]["features"]
    assert 0 < len(features) <= 80  # at most 4 buckets per minute
    ts = [f["properties"]["t"] for f in features]
    assert ts == sorted(set(ts))  # ascending, one feature per bucket
    for t in ts:
        assert 0 < t <= 20
        assert (t / BUCKET_MIN) == round(t / BUCKET_MIN)  # a multiple of 15 s
    for f in features:
        assert f["geometry"]["type"] == "MultiLineString"
        assert all(len(line) == 2 for line in f["geometry"]["coordinates"])


def test_coordinates_have_at_most_five_decimals_and_are_real_nodes(
    walk: WalkService, store: DataStore
) -> None:
    nodes = coord_node(store)
    p = iso(walk, LAT, LON, "opce")
    assert p["origin"]["lat"] == round(LAT, 5)
    assert p["origin"]["lon"] == round(LON, 5)
    for _t, a, b in segments(p):
        for lon, lat in (a, b):
            assert round(lon, 5) == lon
            assert round(lat, 5) == lat
            assert (lon, lat) in nodes  # never an invented point


def test_response_is_strict_json_with_real_integer_facility_ids(
    walk: WalkService, store: DataStore
) -> None:
    body = walk.isochrone(LAT, LON, "starija", 15)
    assert b"NaN" not in body
    assert b"Infinity" not in body
    p = json.loads(body)
    assert p["facilities"]
    for f in p["facilities"]:
        assert isinstance(f["id"], int)
        assert f["id"] in store.facilities.index
        assert f["category"] == store.facilities.loc[f["id"], "category"]
        assert isinstance(f["name"], str)
        assert f["name"]
        assert f["lon"] == pytest.approx(store.facilities.loc[f["id"], "lon"])
        assert 0 < f["t"] <= 15


# ----------------------------------------------------------------------------- isochrone: rules
@pytest.mark.parametrize("persona", ["opce", "starija", "kolica"])
@pytest.mark.parametrize("max_min", [5, 10, 15])
def test_bucket_rule_and_far_end_rule_against_an_independent_dijkstra(
    walk: WalkService, store: DataStore, persona: str, max_min: int
) -> None:
    """Recompute every edge's bucket from a plain unlimited undirected Dijkstra."""
    p = iso(walk, LAT, LON, persona, max_min)
    cfg = store.cfg.personas[persona]
    graph = store.graph.variant(cfg.graph)
    origin = resolve_origin(store, LAT, LON)
    full = dijkstra(graph, directed=False, indices=origin.node)  # no limit, scipy symmetrises
    limit = max_min * 60 * cfg.speed_mps
    lookup = coord_node(store)
    coo = graph.tocoo()
    expected: dict[tuple[tuple[float, float], tuple[float, float]], float] = {}
    for u, v in zip(coo.row.tolist(), coo.col.tolist(), strict=True):
        if u >= v:
            continue
        if origin.snapped_m + max(full[u], full[v]) > limit + 1e-6:
            continue  # far end beyond the limit: must be dropped
        t = (origin.snapped_m + min(full[u], full[v])) / cfg.speed_mps / 60
        key = (
            key5(store, u),
            key5(store, v),
        )
        expected[key] = max(1, math.ceil(t / BUCKET_MIN - 1e-9)) * BUCKET_MIN
    got = {(a, b): t for t, a, b in segments(p)}
    assert len(got) == len(expected) > 100
    assert got.keys() == expected.keys()  # same edges: nothing beyond the limit, nothing missing
    mismatches = [k for k in got if got[k] != pytest.approx(expected[k])]
    assert not mismatches
    assert all(coord in lookup for key in got for coord in key)
    assert max(got.values()) <= max_min


def test_edge_with_far_end_beyond_the_limit_is_absent(walk: WalkService, store: DataStore) -> None:
    """A real edge with one end inside and one end outside the 5-minute limit is dropped."""
    persona = "starija"
    cfg = store.cfg.personas[persona]
    origin = resolve_origin(store, LAT, LON)
    d = dijkstra(store.graph.variant(cfg.graph), directed=False, indices=origin.node)
    limit = 5 * 60 * cfg.speed_mps - origin.snapped_m
    coo = store.graph.variant(cfg.graph).tocoo()
    straddling = [
        (u, v)
        for u, v in zip(coo.row.tolist(), coo.col.tolist(), strict=True)
        if u < v and (d[u] <= limit) != (d[v] <= limit)
    ]
    assert straddling, "the real subgraph must have edges crossing the 5 minute front"
    drawn = {(a, b) for _t, a, b in segments(iso(walk, LAT, LON, persona, 5))}
    for u, v in straddling:
        a = key5(store, u)
        b = key5(store, v)
        assert (a, b) not in drawn
        assert (b, a) not in drawn


def test_buckets_grow_monotonically_with_max_min(walk: WalkService) -> None:
    """Every segment of a shorter isochrone is in the longer one, in the same bucket."""
    small = {(a, b): t for t, a, b in segments(iso(walk, LAT, LON, "opce", 10))}
    large = {(a, b): t for t, a, b in segments(iso(walk, LAT, LON, "opce", 15))}
    assert small
    assert large.keys() > small.keys()
    assert all(large[k] == t for k, t in small.items())
    cumulative = [sum(1 for t in large.values() if t <= step * BUCKET_MIN) for step in range(1, 61)]
    assert cumulative == sorted(cumulative)  # the flood never shrinks
    assert cumulative[-1] == len(large)


def test_wheelchair_reach_is_not_larger_than_the_walking_reach(walk: WalkService) -> None:
    for lat, lon in ORIGINS:
        starija = {(a, b) for _t, a, b in segments(iso(walk, lat, lon, "starija"))}
        kolica = {(a, b) for _t, a, b in segments(iso(walk, lat, lon, "kolica"))}
        opce = {(a, b) for _t, a, b in segments(iso(walk, lat, lon, "opce"))}
        assert kolica <= starija  # same speed, wheelchair graph has fewer edges
        assert len(kolica) <= len(opce)  # in minutes: slower and no steps
        assert starija < opce
    fac_k = {f["id"] for f in iso(walk, LAT, LON, "kolica")["facilities"]}
    fac_s = {f["id"] for f in iso(walk, LAT, LON, "starija")["facilities"]}
    assert fac_k <= fac_s


# ----------------------------------------------------------------------------- isochrone vs /access
@pytest.mark.parametrize("persona", PERSONAS)
def test_facilities_and_counts_match_access_minutes(
    walk: WalkService, store: DataStore, persona: str
) -> None:
    for lat, lon in ORIGINS:
        access = service.compute_access(store, round(lat, 5), round(lon, 5), persona)
        p = iso(walk, lat, lon, persona, 20)
        by_cat: dict[str, list[float]] = {}
        for f in p["facilities"]:
            by_cat.setdefault(f["category"], []).append(f["t"])
        checked = 0
        for row in access["categories"]:
            cat, m = row["category"], row["minutes"]
            times = by_cat.get(cat, [])
            if m is None or m > 20:
                assert not times or min(times) > 19.9
                continue
            assert min(times) == pytest.approx(m, abs=0.1), (cat, persona)
            checked += 1
            for threshold in (5, 10, 15, 20):
                n = p["counts"][str(threshold)].get(cat, 0)
                assert n == sum(1 for t in times if t <= threshold)
                if m <= threshold - 0.1:
                    assert n >= 1, (cat, threshold, m)  # nearest is in reach
                if m > threshold + 0.1:
                    assert n == 0, (cat, threshold, m)  # nothing closer than /access says
        assert checked >= 5


def test_counts_are_cumulative_and_limited_to_max_min(walk: WalkService) -> None:
    p = iso(walk, LAT, LON, "opce", 20)
    assert list(p["counts"]) == ["5", "10", "15", "20"]
    for cat in CATEGORIES:
        series = [p["counts"][k].get(cat, 0) for k in ("5", "10", "15", "20")]
        assert series == sorted(series)
    assert sum(p["counts"]["20"].values()) == len(p["facilities"])
    assert list(iso(walk, LAT, LON, "opce", 7)["counts"]) == ["5"]


def test_counts_of_a_short_isochrone_equal_those_of_a_long_one(walk: WalkService) -> None:
    short = iso(walk, LAT, LON, "roditelj", 10)
    long = iso(walk, LAT, LON, "roditelj", 20)
    assert short["counts"]["5"] == long["counts"]["5"]
    assert short["counts"]["10"] == long["counts"]["10"]


def test_a_snap_distance_beyond_the_time_budget_gives_an_empty_isochrone(
    store: DataStore, walk: WalkService
) -> None:
    """~250 m from the network: starija walks 270 m in 5 min -> little or no reach, no crash."""
    origin = resolve_origin(store, LAT, LON)
    far = type(origin)(origin.lat, origin.lon, origin.node, 400.0)
    p = compute_isochrone(store, walk.index, far, "starija", 5)
    assert p["buckets"]["features"] == []
    assert p["facilities"] == []
    assert p["counts"] == {"5": {}}


# ----------------------------------------------------------------------------- isochrone: cache, errors
def test_cache_hit_returns_the_same_payload_and_rounds_the_key(store: DataStore) -> None:
    service_ = WalkService(store)
    first = service_.isochrone(LAT, LON, "starija", 15)
    assert len(service_._isochrones) == 1
    again = service_.isochrone(LAT, LON, "starija", 15)
    assert again is first  # the very same cached bytes
    near = service_.isochrone(LAT + 0.000001, LON - 0.000001, "starija", 15)  # < 5 decimals apart
    assert near is first
    assert len(service_._isochrones) == 1
    other = service_.isochrone(LAT, LON, "opce", 15)
    assert other != first
    assert len(service_._isochrones) == 2
    service_.isochrone(LAT, LON, "starija", 10)
    assert len(service_._isochrones) == 3
    route_a = service_.route(LAT, LON, "starija", "ljekarna")
    assert service_.route(LAT, LON, "starija", "ljekarna") is route_a


def test_lru_evicts_the_least_recently_used() -> None:
    cache: LruCache[int] = LruCache(2)
    calls: list[str] = []

    def make(key: str, value: int) -> int:
        calls.append(key)
        return value

    assert cache.get_or_compute("a", lambda: make("a", 1)) == 1
    assert cache.get_or_compute("b", lambda: make("b", 2)) == 2
    assert cache.get_or_compute("a", lambda: make("a", 9)) == 1  # hit, "a" is fresh again
    assert cache.get_or_compute("c", lambda: make("c", 3)) == 3  # evicts "b"
    assert cache.get_or_compute("b", lambda: make("b", 4)) == 4
    assert calls == ["a", "b", "c", "b"]
    assert len(cache) == 2


def test_origin_validation_matches_access(
    store: DataStore, monkeypatch: pytest.MonkeyPatch
) -> None:
    with pytest.raises(service.FarFromNetworkError) as err:
        resolve_origin(store, LAT, LON + 0.04)
    assert err.value.snapped_m > 300
    box = Polygon([(15.0, 45.0), (15.5, 45.0), (15.5, 45.5), (15.0, 45.5)])
    monkeypatch.setattr(store, "boundary", prep(box))
    with pytest.raises(service.OutsideZagrebError):
        resolve_origin(store, LAT, LON)


# ----------------------------------------------------------------------------- route
@pytest.mark.parametrize("persona", PERSONAS)
def test_route_minutes_and_distance_equal_access(
    walk: WalkService, store: DataStore, persona: str
) -> None:
    for lat, lon in ORIGINS:
        access = service.compute_access(store, round(lat, 5), round(lon, 5), persona)
        for row in access["categories"]:
            cat = row["category"]
            r = json.loads(walk.route(lat, lon, persona, cat))
            assert r["minutes"] == pytest.approx(row["minutes"], abs=0.1), (cat, persona)
            assert abs(r["distance_m"] - row["distance_m"]) <= 1
            assert r["category"] == cat
            assert r["persona"] == persona
            assert r["facility"]["category"] == cat


@pytest.mark.parametrize("persona", PERSONAS)
def test_route_is_a_connected_path_between_the_snapped_nodes(
    walk: WalkService, store: DataStore, persona: str
) -> None:
    cfg = store.cfg.personas[persona]
    graph = store.graph.variant(cfg.graph).tocsr()
    lookup = coord_node(store)
    for lat, lon in ORIGINS:
        origin = resolve_origin(store, lat, lon)
        for cat in CATEGORIES:
            r = json.loads(walk.route(lat, lon, persona, cat))
            path = [lookup[(lo, la)] for lo, la in r["coordinates"]]
            assert len(path) >= 2
            assert path[0] == origin.node  # starts at the snapped node
            fn = walk.index.facilities(cat)
            fid = r["facility"]["id"]
            ends = fn.nodes[fn.ids[fn.owner] == fid]
            assert path[-1] in set(ends.tolist())  # ends at the facility's access node
            length = 0.0
            for a, b in zip(path, path[1:], strict=False):
                if a == b:
                    continue  # the 2-point form of a zero-length route
                w = graph[a, b]
                assert w > 0, "consecutive route nodes must share a graph edge"
                length += float(w)
            assert origin.snapped_m + length == pytest.approx(r["distance_m"], abs=1.0)
            assert r["minutes"] == pytest.approx(
                (origin.snapped_m + length) / cfg.speed_mps / 60, abs=0.06
            )


def test_wheelchair_route_is_not_shorter_than_the_walking_route(walk: WalkService) -> None:
    detours = 0
    for lat, lon in ORIGINS:
        for cat in CATEGORIES:
            starija = json.loads(walk.route(lat, lon, "starija", cat))
            kolica = json.loads(walk.route(lat, lon, "kolica", cat))
            opce = json.loads(walk.route(lat, lon, "opce", cat))
            assert kolica["minutes"] >= starija["minutes"] - 0.05  # same speed, fewer edges
            assert kolica["minutes"] >= opce["minutes"]
            detours += kolica["minutes"] > starija["minutes"] + 0.5
    assert detours >= 1, "the real box has hundreds of steps: some route needs a detour"


def test_route_to_a_given_facility(walk: WalkService, store: DataStore) -> None:
    nearest = json.loads(walk.route(LAT, LON, "opce", "ljekarna"))
    same = json.loads(walk.route(LAT, LON, "opce", None, nearest["facility"]["id"]))
    assert same == nearest
    snapped_ids = {int(i) for i in walk.index.facilities("ljekarna").ids}
    farther = []
    for fid in sorted(snapped_ids - {nearest["facility"]["id"]}):
        try:
            farther.append(json.loads(walk.route(LAT, LON, "opce", "ljekarna", fid)))
        except NotReachableError:
            continue  # on a fragment of the clipped real subgraph, not connected to the origin
    assert len(farther) >= 3
    assert all(f["minutes"] >= nearest["minutes"] for f in farther)
    assert all(f["facility"]["id"] != nearest["facility"]["id"] for f in farther)


def test_route_errors(store: DataStore, walk: WalkService) -> None:
    origin = resolve_origin(store, LAT, LON)
    with pytest.raises(InvalidRequestError):  # neither category nor facility
        compute_route(store, walk.index, origin, "opce")
    pharmacy = int(store.facilities[store.facilities["category"] == "ljekarna"].index[0])
    with pytest.raises(InvalidRequestError):  # facility of another category
        compute_route(store, walk.index, origin, "opce", "park", pharmacy)
    with pytest.raises(NotReachableError):  # unknown facility
        compute_route(store, walk.index, origin, "opce", None, 10**9)


def test_route_for_a_category_without_data_is_not_reachable(subgraph) -> None:  # type: ignore[no-untyped-def]
    from conftest import build_store

    without_park = build_store(subgraph, drop_category="park")
    origin = resolve_origin(without_park, LAT, LON)
    with pytest.raises(NotReachableError, match="nema učitanih podataka"):
        compute_route(without_park, WalkIndex(without_park), origin, "opce", "park")


def test_a_facility_on_the_origin_node_gives_a_valid_two_point_line(
    store: DataStore, walk: WalkService
) -> None:
    fn = walk.index.facilities("ljekarna")
    node = int(fn.nodes[0])
    fid = int(fn.ids[fn.owner[0]])
    lat, lon = float(store.graph.lat[node]), float(store.graph.lon[node])
    r = json.loads(walk.route(lat, lon, "opce", None, fid))
    assert len(r["coordinates"]) == 2  # one node, repeated: still a valid LineString
    assert r["coordinates"][0] == r["coordinates"][1]
    assert r["distance_m"] <= 1
    assert r["minutes"] <= 0.1


# ----------------------------------------------------------------------------- HTTP
@pytest.fixture
def client(store: DataStore, client_factory) -> Iterator[TestClient]:  # type: ignore[no-untyped-def]
    with client_factory(lambda: store) as c:
        yield c


def test_http_isochrone_and_route(client: TestClient) -> None:
    r = client.get(
        "/api/v1/isochrone", params={"lat": LAT, "lon": LON, "persona": "starija", "max_min": 15}
    )
    assert r.status_code == 200
    assert r.headers["content-type"] == "application/json"
    body = r.json()
    assert body["max_min"] == 15
    assert body["persona"] == "starija"
    assert (
        client.get(
            "/api/v1/isochrone", params={"lat": LAT, "lon": LON, "persona": "starija"}
        ).json()
        == body
    )  # default max_min is 15, and the cached response is identical
    rt = client.get(
        "/api/v1/route",
        params={"lat": LAT, "lon": LON, "persona": "starija", "category": "ljekarna"},
    )
    assert rt.status_code == 200
    route = rt.json()
    access = client.get(
        "/api/v1/access", params={"lat": LAT, "lon": LON, "persona": "starija"}
    ).json()
    pharmacy = next(c for c in access["categories"] if c["category"] == "ljekarna")
    assert route["minutes"] == pytest.approx(pharmacy["minutes"], abs=0.1)
    assert set(route) >= {"minutes", "distance_m", "facility", "coordinates", "origin"}
    assert set(route["facility"]) >= {"id", "category", "name", "lon", "lat"}


def test_http_422_and_404_are_problem_json(client: TestClient) -> None:
    base = {"lat": LAT, "lon": LON, "persona": "opce"}
    bad_requests = [
        ("/api/v1/isochrone", {**base, "max_min": 4}),
        ("/api/v1/isochrone", {**base, "max_min": 21}),
        ("/api/v1/isochrone", {**base, "max_min": "x"}),
        ("/api/v1/isochrone", {**base, "persona": "robot"}),
        ("/api/v1/isochrone", {**base, "lat": 48.85, "lon": 2.35}),  # Paris
        ("/api/v1/isochrone", {**base, "lon": LON + 0.04}),  # > 300 m from the network
        ("/api/v1/route", {**base, "category": "zzz"}),
        ("/api/v1/route", {**base}),  # neither category nor facility_id
        ("/api/v1/route", {**base, "category": "park", "lon": LON + 0.04}),
        ("/api/v1/route", {**base, "category": "park", "facility_id": -1}),
        ("/api/v1/route", {**base, "category": "park", "facility_id": 1}),  # not a park or unknown
    ]
    for url, params in bad_requests:
        r = client.get(url, params=params)
        assert r.status_code in (404, 422), (url, params, r.status_code)
        assert r.headers["content-type"].startswith("application/problem+json"), (url, params)
    far = client.get("/api/v1/isochrone", params={**base, "lon": LON + 0.04})
    assert far.status_code == 422
    assert "daleko od pješačke mreže" in far.json()["detail"]
    missing = client.get("/api/v1/route", params={**base, "facility_id": 10**9})
    assert missing.status_code == 404
    assert missing.json()["status"] == 404
    neither = client.get("/api/v1/route", params=base)
    assert neither.status_code == 422
    assert "category" in neither.json()["detail"]


def test_http_503_before_data_is_loaded(client_factory) -> None:  # type: ignore[no-untyped-def]
    def broken() -> DataStore:
        raise RuntimeError("no data")

    with client_factory(broken) as c:
        for url in (
            "/api/v1/isochrone?lat=45.81&lon=15.97&persona=opce",
            "/api/v1/route?lat=45.81&lon=15.97&persona=opce&category=park",
        ):
            r = c.get(url)
            assert r.status_code == 503
            assert r.headers["content-type"].startswith("application/problem+json")


def test_openapi_documents_the_new_endpoints(client: TestClient) -> None:
    spec = client.get("/openapi.json").json()
    for path in ("/api/v1/isochrone", "/api/v1/route"):
        op = spec["paths"][path]["get"]
        assert len(op["description"]) > 80
        assert "persona" in {p["name"] for p in op["parameters"]}
        assert op["responses"]["200"]["content"]["application/json"]["schema"]
    params = {p["name"]: p for p in spec["paths"]["/api/v1/isochrone"]["get"]["parameters"]}
    assert params["max_min"]["schema"]["minimum"] == 5
    assert params["max_min"]["schema"]["maximum"] == 20
    assert "cells" in spec["paths"]["/api/v1/plan/optimise"]["post"]["description"]


# ----------------------------------------------------------------------------- optimise cells
@pytest.mark.parametrize("category", ["vrtic", "ljekarna", "park", "lijecnik"])
@pytest.mark.parametrize("persona", ["opce", "roditelj", "kolica"])
def test_optimise_cells_sum_to_total_newly_covered(
    planner: Planner, store: DataStore, category: str, persona: str
) -> None:
    for k in (1, 3, 5):
        result = planner.optimise(category, persona, k)
        cells = result["cells"]
        assert [c["cell_id"] for c in cells] == store.cells["grd_id"].tolist()
        assert set(cells[0]) == {
            "cell_id",
            "unmet_before",
            "unmet_after",
            "need_before",
            "need_after",
        }
        gain = sum(c["unmet_before"] - c["unmet_after"] for c in cells)
        assert gain == pytest.approx(result["total_newly_covered"], abs=1.0)
        for c in cells:
            assert 0 <= c["unmet_after"] <= c["unmet_before"]
            assert 0 <= c["need_after"] <= c["need_before"]


def test_optimise_cells_use_the_optimisers_node_coverage(
    planner: Planner, store: DataStore
) -> None:
    result = planner.optimise("vrtic", "roditelj", 3)
    cells = result["cells"]
    people = planner._node_state("vrtic", "roditelj")["people"].sum()
    before = sum(c["unmet_before"] for c in cells)
    after = sum(c["unmet_after"] for c in cells)
    # shares are people-based on the same nodes: unmet people = (1 - share) * all people
    assert before == pytest.approx((1 - result["share_before"]) * people, abs=0.5)
    assert after == pytest.approx((1 - result["share_after"]) * people, abs=0.5)
    # need_before is exactly the unmet value of /plan/need
    need = {
        f["properties"]["grd_id"]: f["properties"]["unmet"]
        for f in planner.need("vrtic", "roditelj")["features"]
    }
    for c in cells:
        assert c["need_before"] == pytest.approx(need[c["cell_id"]], abs=0.06)
    # at least one cell improves, and cells without improvement are unchanged
    assert any(c["unmet_after"] < c["unmet_before"] for c in cells)


def test_more_sites_never_leave_a_cell_worse_off(planner: Planner) -> None:
    one = {c["cell_id"]: c for c in planner.optimise("vrtic", "roditelj", 1)["cells"]}
    three = {c["cell_id"]: c for c in planner.optimise("vrtic", "roditelj", 3)["cells"]}
    for cell_id, c in three.items():
        assert c["unmet_before"] == one[cell_id]["unmet_before"]  # the baseline is the same
        assert c["unmet_after"] <= one[cell_id]["unmet_after"] + 1e-9  # greedy: superset of sites


def test_http_optimise_returns_cells(client: TestClient) -> None:
    r = client.post(
        "/api/v1/plan/optimise", json={"category": "vrtic", "persona": "roditelj", "k": 3}
    )
    assert r.status_code == 200
    body = r.json()
    gain = sum(c["unmet_before"] - c["unmet_after"] for c in body["cells"])
    assert gain == pytest.approx(body["total_newly_covered"], abs=1.0)
    assert all(math.isfinite(c["unmet_before"]) for c in body["cells"])


# ----------------------------------------------------------------------------- performance (fixture)
def test_warm_isochrone_is_fast_and_small_on_the_fixture(walk: WalkService) -> None:
    walk.isochrone(LAT, LON, "opce", 20)
    t0 = time.perf_counter()
    for _ in range(20):
        body = walk.isochrone(LAT, LON, "opce", 20)
    assert (time.perf_counter() - t0) / 20 < 0.1
    assert len(body) <= 1_000_000
    # the same on a cold computation (cache bypassed)
    origin = resolve_origin(walk.store, LAT, LON)
    t0 = time.perf_counter()
    payload = compute_isochrone(walk.store, walk.index, origin, "opce", 20)
    assert time.perf_counter() - t0 < 0.5
    assert len(payload["buckets"]["features"]) <= 80
    assert np.isfinite(len(body))
