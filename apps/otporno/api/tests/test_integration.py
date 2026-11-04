"""API on PostGIS with real Karlovac data (census grid cells, OSM public buildings, 24 recorded Open-Meteo
grid points) and the recorded Open-Meteo response. Needs TEST_DATABASE_URL (database name ending in _test)."""

from __future__ import annotations

import os
import time
from typing import Any

import pytest
import respx
from conftest import FIXTURES
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy.orm import Session, sessionmaker

from otporno_api.app import create_otporno_app
from otporno_api.constants import FLOOD_DISCLAIMER, FLOOD_UNAVAILABLE, HV_LAYERS
from otporno_api.settings import OtpornoSettings

pytestmark = pytest.mark.db

KARLOVAC = "HR_01791"
# Karlovac: the confluence of the Kupa and Korana rivers (flood-prone area) and the castle of Dubovac on a hill.
# Which of them lies in an HV hazard zone cannot be decided by the app (ladder c), so both must get the same
# honest flood answer; the heat answer is what differs in input.
KUPA = (45.4887, 15.5517)
DUBOVAC = (45.4959, 15.5431)
ZAGREB_IN_CROATIA = (45.8131, 15.9772)
PARIS = (48.8566, 2.3522)


@pytest.fixture(scope="module")
def client(seeded: sessionmaker[Session], om_response: dict[str, Any], dhmz_xml: bytes) -> Any:
    settings = OtpornoSettings(
        _env_file=None,
        database_url=os.environ["TEST_DATABASE_URL"],
        contact_email="test@example.org",
        rate_limit="1000/minute",
    )
    from opendata_core.db import make_engine, make_session_dependency
    from otporno_api.dhmz import DhmzLive

    live = DhmzLive(lambda: dhmz_xml, clock=lambda: 0.0)
    app = create_otporno_app(settings, make_session_dependency(make_engine(settings)), seeded, live)
    with respx.mock(assert_all_called=False) as router:
        router.get(settings.open_meteo_climate_url).mock(
            return_value=Response(200, json=om_response, headers={"x-ratelimit-cost": "939.2"})
        )

        def corine(request: Any) -> Response:
            # layers=all:0 is the neighbourhood query, layers=all the point query (both recorded 2026-11-04)
            wanted = "karlovac_500m" if request.url.params.get("layers") == "all:0" else "karlovac"
            body = (FIXTURES / f"2026-11-04_corine_identify_{wanted}.json").read_text(
                encoding="utf-8"
            )
            return Response(200, content=body, headers={"content-type": "application/json"})

        router.get(url__startswith=settings.corine_url).mock(side_effect=corine)
        yield TestClient(app)


def passport(client: TestClient, point: tuple[float, float]) -> Any:
    return client.get("/api/v1/passport", params={"lat": point[0], "lon": point[1]})


@pytest.mark.parametrize("point", [KUPA, DUBOVAC])
def test_passport_in_karlovac_states_the_flood_ladder_honestly(
    client: TestClient, point: tuple[float, float]
) -> None:
    r = passport(client, point)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["location"]["municipality"]["lau_id"] == KARLOVAC
    f = body["flood"]
    assert f["level"] is None
    assert f["band"] is None
    assert f["ladder"] == "c"
    assert f["message"] == FLOOD_UNAVAILABLE
    assert f["disclaimer"] == FLOOD_DISCLAIMER
    assert f["map_year"] == 2019
    assert f["wms"]["layers"] == HV_LAYERS
    assert body["fire"]["status"] == "ready"


def test_passport_heat_block_for_a_point_without_cache_uses_one_request(client: TestClient) -> None:
    started = time.perf_counter()
    r = passport(client, KUPA)
    cold = time.perf_counter() - started
    h = r.json()["heat"]
    assert h["status"] == "ready"
    assert h["band"] in {"niska", "umjerena", "visoka", "vrlo visoka"}
    assert (
        h["future_hot_days"]["min"] <= h["future_hot_days"]["mean"] <= h["future_hot_days"]["max"]
    )
    assert h["base_hot_days"] > 0
    assert len(h["models"]) == 3
    assert h["confidence"] in {"visoka", "srednja", "niska"}
    assert "Open-Meteo.com" in h["attribution"]
    assert h["grid_points"] >= 20
    assert cold < 2.0, f"cold passport took {cold:.2f}s"


def test_second_passport_is_served_from_the_cache_quickly(client: TestClient) -> None:
    passport(client, DUBOVAC)
    started = time.perf_counter()
    r = passport(client, DUBOVAC)
    warm = time.perf_counter() - started
    assert r.status_code == 200
    assert warm < 0.3, f"cached passport took {warm:.3f}s"


def test_passport_lists_cited_actions(client: TestClient) -> None:
    body = passport(client, KUPA).json()
    for hazard in ("flood", "heat"):
        acts = body["actions"][hazard]
        assert 1 <= len(acts) <= 6
        for a in acts:
            assert a["text"]
            assert a["source_url"].startswith("https://")
            assert a["source_title"]


def test_passport_outside_croatia_is_422(client: TestClient) -> None:
    r = passport(client, PARIS)
    assert r.status_code == 422
    assert "Hrvatsk" in r.json()["detail"]


def test_passport_inside_the_box_but_not_in_a_municipality_is_422(client: TestClient) -> None:
    # open Adriatic west of Istria: inside the bounding box of Croatia, in no municipality
    assert client.get("/api/v1/passport", params={"lat": 44.0, "lon": 13.2}).status_code == 422


def test_exposure_reconciles_with_the_cell_geojson(client: TestClient) -> None:
    exp = client.get(f"/api/v1/municipalities/{KARLOVAC}/exposure").json()
    cells = client.get("/api/v1/cells", params={"lau": KARLOVAC}).json()
    assert exp["status"] == "ready"
    heat = exp["hazards"]["heat"]
    assert heat["status"] == "ready"
    band_pop = sum(b["pop_total"] for b in heat["bands"]) + heat["without_data"]["pop_total"]
    band_65 = sum(b["pop_65p"] for b in heat["bands"]) + heat["without_data"]["pop_65p"]
    feats = cells["features"]
    assert (
        band_pop
        == exp["municipality"]["pop_total"]
        == sum(f["properties"]["pop_total"] for f in feats)
        == cells["summary"]["pop_total"]
    )
    assert (
        band_65 == exp["municipality"]["pop_65p"] == sum(f["properties"]["pop_65p"] for f in feats)
    )
    high65 = sum(
        f["properties"]["pop_65p"]
        for f in feats
        if f["properties"]["heat_band"] in {"visoka", "vrlo visoka"}
    )
    assert exp["kpis"]["heat_high_pop_65p"] == high65
    assert exp["kpis"]["flood_high_pop"] is None
    assert exp["hazards"]["flood"]["status"] == "unavailable"


def test_cells_priority_changes_with_weights_and_validates_them(client: TestClient) -> None:
    a = client.get(
        "/api/v1/cells", params={"lau": KARLOVAC, "w_flood": 0.5, "w_heat": 0.35, "w_fire": 0.15}
    ).json()
    b = client.get(
        "/api/v1/cells", params={"lau": KARLOVAC, "w_flood": 0.0, "w_heat": 1.0, "w_fire": 0.0}
    ).json()
    # flood and fire carry no data, so renormalisation makes both weightings identical
    assert [f["properties"]["priority"] for f in a["features"]] == [
        f["properties"]["priority"] for f in b["features"]
    ]
    assert max(f["properties"]["priority"] for f in a["features"]) > 0
    assert client.get("/api/v1/cells", params={"lau": KARLOVAC, "w_flood": 0.9}).status_code == 422
    assert client.get("/api/v1/cells", params={"lau": "HR_00000"}).status_code == 404


def test_cooling_default_demand_is_empty_where_no_cell_is_in_a_high_heat_band(
    client: TestClient,
) -> None:
    # real data: Karlovac's ensemble future hot days rank in band "umjerena" against the recorded grid points
    r = client.post("/api/v1/cooling-centres", json={"lau_id": KARLOVAC, "k": 3})
    assert r.status_code == 409
    assert "niži pojas" in r.json()["detail"]


def test_cooling_centres_cover_at_least_what_was_covered_before(client: TestClient) -> None:
    previous = -1
    for k in (1, 3, 5):
        r = client.post(
            "/api/v1/cooling-centres", json={"lau_id": KARLOVAC, "k": k, "min_band": "umjerena"}
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["covered_after"] >= body["covered_before"]
        assert len(body["sites"]) <= k
        assert body["covered_after"] >= previous
        assert body["covered_after"] <= body["demand_total"]
        previous = body["covered_after"]
    assert (
        client.post("/api/v1/cooling-centres", json={"lau_id": KARLOVAC, "k": 6}).status_code == 422
    )


def test_municipality_search_and_unknown_municipality(client: TestClient) -> None:
    res = client.get("/api/v1/municipalities", params={"q": "karlo"}).json()["results"]
    assert res
    assert res[0]["lau_id"] == KARLOVAC
    assert res[0]["pop_total"] > 40000
    assert client.get("/api/v1/municipalities/HR_00000/exposure").status_code == 404


def test_compute_is_idempotent_for_a_ready_municipality(client: TestClient) -> None:
    first = client.post(f"/api/v1/municipalities/{KARLOVAC}/compute")
    second = client.post(f"/api/v1/municipalities/{KARLOVAC}/compute")
    assert first.status_code == second.status_code == 200
    assert first.json()["status"] == "ready"
    assert first.json()["started"] is False


def test_sources_endpoint_lists_the_registered_sources(client: TestClient) -> None:
    ids = {s["id"] for s in client.get("/api/v1/sources").json()["sources"]}
    assert {
        "hv-flood-2019",
        "open-meteo-climate",
        "eurostat-census-grid-2021",
        "osm-public-buildings",
    } <= ids


def test_live_dhmz_returns_nearest_stations_or_hides_stale_data(client: TestClient) -> None:
    r = client.get("/api/v1/live/dhmz", params={"lat": KUPA[0], "lon": KUPA[1]})
    assert r.status_code == 200
    body = r.json()
    # the recorded feed is from 2026-11-04 22:00; later runs see it as older than 3 hours and must hide it
    assert body["status"] in {"ok", "stale"}
    if body["status"] == "ok":
        assert body["stations"][0]["name"] == "Karlovac"
    else:
        assert body["stations"] == []
        assert "3 sata" in body["message"]
    assert body["observed_at"].startswith("2026-11-04T22:00")
    assert client.get("/api/v1/live/dhmz", params={"lat": 45.5}).status_code == 422


def test_brief_is_html_and_reconciles_with_exposure(client: TestClient) -> None:
    r = client.get(f"/api/v1/municipalities/{KARLOVAC}/brief")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    exp = client.get(f"/api/v1/municipalities/{KARLOVAC}/exposure").json()
    pop = f"{exp['municipality']['pop_total']:,}".replace(",", ".")
    assert "Karlovac" in r.text
    assert pop in r.text
    assert "Hrvatske vode ne jamče" in r.text
    assert r.text.count("Izvor: <a href=") >= 3
    assert client.get("/api/v1/municipalities/HR_00000/brief").status_code == 404


def test_passport_fire_block_uses_corine_and_lists_cited_actions(client: TestClient) -> None:
    body = passport(client, KUPA).json()
    fire = body["fire"]
    assert fire["status"] == "ready"
    # recorded response: the centre of Karlovac is "112 Discontinuous urban fabric"; no vegetation within 500 m
    assert fire["land_cover"]["code"] == 112
    assert fire["band"] == "niska"
    assert fire["confidence"] == "niska"
    assert "Copernicus" in fire["attribution"]
    acts = body["actions"]["fire"]
    assert 1 <= len(acts) <= 6
    assert all(a["source_url"].startswith("https://") for a in acts)
    assert any(s["id"] == "corine-2018" for s in body["sources"])
