"""CKAN client tests against recorded REAL responses from data.gov.hr (2026-11-03)."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import respx

from opendata_core import ckan
from opendata_core.config import CoreSettings

D = "2026-11-03"


def _load(fixtures_dir: Path, name: str) -> Any:
    return json.loads((fixtures_dir / "ckan" / f"{D}_{name}.json").read_text(encoding="utf-8"))


@pytest.fixture
def client(settings: CoreSettings, no_sleep: list[float]) -> ckan.CkanClient:
    # No throttling in unit tests; the throttle itself is tested separately.
    return ckan.CkanClient(settings, throttle=ckan._Throttle(0))


@respx.mock
def test_status_show(client: ckan.CkanClient, fixtures_dir: Path) -> None:
    respx.get(f"{ckan.BASE}/status_show").respond(200, json=_load(fixtures_dir, "status_show"))
    result = client.status_show()
    assert result["ckan_version"] == "2.9.9"


@respx.mock
def test_package_search_sends_params_and_drops_none(
    client: ckan.CkanClient, fixtures_dir: Path
) -> None:
    route = respx.get(f"{ckan.BASE}/package_search").respond(
        200, json=_load(fixtures_dir, "package_search")
    )
    result = client.package_search("ljekarne", rows=3)
    q = dict(route.calls.last.request.url.params)
    assert q == {"q": "ljekarne", "rows": "3", "start": "0"}  # fq=None is not sent
    assert result["count"] == 3
    assert result["results"][0]["name"] == "geoportal-ljekarne"


@respx.mock
def test_package_search_with_fq(client: ckan.CkanClient, fixtures_dir: Path) -> None:
    route = respx.get(f"{ckan.BASE}/package_search").respond(
        200, json=_load(fixtures_dir, "package_search")
    )
    client.package_search("x", fq="organization:zagreb")
    assert route.calls.last.request.url.params["fq"] == "organization:zagreb"


@respx.mock
def test_package_show_and_resource_show(client: ckan.CkanClient, fixtures_dir: Path) -> None:
    respx.get(f"{ckan.BASE}/package_show").respond(200, json=_load(fixtures_dir, "package_show"))
    pkg = client.package_show("geoportal-ljekarne")
    assert pkg["id"] == "6d6f96f1-b0a4-4b8d-9fdd-03284e86738b"
    respx.get(f"{ckan.BASE}/resource_show").respond(200, json=_load(fixtures_dir, "resource_show"))
    res = client.resource_show("266882bf-0eb9-452c-97b6-0f99a464e64a")
    assert res["format"] == "GeoJSON"


@respx.mock
def test_not_found_raises_ckan_error_with_portal_message(
    client: ckan.CkanClient, fixtures_dir: Path
) -> None:
    respx.get(f"{ckan.BASE}/package_show").respond(
        404, json=_load(fixtures_dir, "package_show_notfound")
    )
    with pytest.raises(ckan.CkanError) as err:
        client.package_show("this-does-not-exist-xyz")
    assert err.value.status_code == 404
    assert err.value.payload["success"] is False
    assert "HTTP 404" in str(err.value)


@respx.mock
def test_success_false_with_http_200_raises(client: ckan.CkanClient) -> None:
    respx.get(f"{ckan.BASE}/status_show").respond(200, json={"success": False, "error": {}})
    with pytest.raises(ckan.CkanError, match="success"):
        client.status_show()


@respx.mock
def test_html_response_raises_ckan_error(client: ckan.CkanClient) -> None:
    # The portal's root /api/3 answers with HTML (the real API is under /ckan/).
    respx.get(f"{ckan.BASE}/status_show").respond(
        200, text="<html></html>", headers={"content-type": "text/html"}
    )
    with pytest.raises(ckan.CkanError, match="not JSON"):
        client.status_show()


def test_newest_resource_orders_by_last_modified_then_created(fixtures_dir: Path) -> None:
    pkg = _load(fixtures_dir, "package_show")["result"]
    best = ckan.newest_resource(pkg, ["geojson"])  # case-insensitive
    assert best is not None
    assert best["id"] == "266882bf-0eb9-452c-97b6-0f99a464e64a"
    # among CSV/KML/GeoJSON the GeoJSON one has the latest last_modified (2023-02-01)
    overall = ckan.newest_resource(pkg, ["CSV", "KML", "GeoJSON"])
    assert overall is not None
    assert overall["format"] == "GeoJSON"
    assert ckan.newest_resource(pkg, ["XLSX"]) is None


def test_newest_resource_tie_break_and_missing_dates() -> None:
    pkg = {
        "resources": [
            {
                "id": "a",
                "format": "CSV",
                "last_modified": "2024-01-01T00:00:00",
                "created": "2023-01-01T00:00:00",
            },
            {
                "id": "b",
                "format": "CSV",
                "last_modified": "2024-01-01T00:00:00",
                "created": "2023-06-01T00:00:00",
            },
            {"id": "c", "format": "CSV", "last_modified": None, "created": "2030-01-01T00:00:00"},
            {"id": "d", "format": "CSV"},
        ]
    }
    best = ckan.newest_resource(pkg, ["csv"])
    assert best is not None
    assert best["id"] == "b"  # same last_modified as a, later created; c has no last_modified


@respx.mock
def test_download(client: ckan.CkanClient, tmp_path: Path) -> None:
    payload = b'{"type":"FeatureCollection","features":[]}'
    respx.get("https://files.test/a.json").respond(200, content=payload)
    path, sha = client.download("https://files.test/a.json", tmp_path / "a.json")
    assert path.read_bytes() == payload
    assert sha == hashlib.sha256(payload).hexdigest()


def test_throttle_enforces_min_interval(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    clock = [100.0]

    def fake_sleep(s: float) -> None:
        sleeps.append(s)
        clock[0] += s

    monkeypatch.setattr(ckan, "time", SimpleNamespace(monotonic=lambda: clock[0], sleep=fake_sleep))
    t = ckan._Throttle(0.5)
    t.wait()  # first call: no wait (last = 0)
    t.wait()  # immediately again: must wait 0.5
    clock[0] += 0.2
    t.wait()  # 0.2 s elapsed: must wait the remaining 0.3
    assert sleeps == [pytest.approx(0.5), pytest.approx(0.3)]


@respx.mock
def test_module_level_functions_use_default_client(
    monkeypatch: pytest.MonkeyPatch,
    settings: CoreSettings,
    fixtures_dir: Path,
    no_sleep: list[float],
) -> None:
    monkeypatch.setattr(ckan, "_default", ckan.CkanClient(settings, throttle=ckan._Throttle(0)))
    respx.get(f"{ckan.BASE}/status_show").respond(200, json=_load(fixtures_dir, "status_show"))
    respx.get(f"{ckan.BASE}/package_show").respond(200, json=_load(fixtures_dir, "package_show"))
    respx.get(f"{ckan.BASE}/package_search").respond(
        200, json=_load(fixtures_dir, "package_search")
    )
    respx.get(f"{ckan.BASE}/resource_show").respond(200, json=_load(fixtures_dir, "resource_show"))
    respx.get("https://files.test/x").respond(200, content=b"x")
    assert ckan.status_show()["ckan_version"] == "2.9.9"
    assert ckan.package_show("p")["name"] == "geoportal-ljekarne"
    assert ckan.package_search("q")["count"] == 3
    assert ckan.resource_show("r")["format"] == "GeoJSON"
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        path, _ = ckan.download("https://files.test/x", Path(d) / "x")
        assert path.read_bytes() == b"x"


def test_ckan_error_attributes() -> None:
    e = ckan.CkanError("m", status_code=500, payload={"a": 1})
    assert (e.status_code, e.payload) == (500, {"a": 1})
    assert isinstance(e, Exception)
    assert httpx  # imported for type parity with the client module
