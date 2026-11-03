"""Geocode tests using a recorded REAL Nominatim response (2026-11-03)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
import respx
from sqlalchemy.orm import Session

from opendata_core import geocode
from opendata_core.config import CoreSettings

URL = "https://nominatim.openstreetmap.org/search"
_REAL_THROTTLE = geocode._throttle  # the autouse fixture below replaces the module attribute


@pytest.fixture
def real_response(fixtures_dir: Path) -> list[dict[str, object]]:
    path = fixtures_dir / "nominatim" / "2026-11-03_search_trg_bana_jelacica.json"
    return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]


@pytest.fixture(autouse=True)
def _no_throttle(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(geocode, "_throttle", lambda: None)


@respx.mock
def test_search_params_and_attribution(
    session: Session, settings: CoreSettings, real_response: list[dict[str, object]]
) -> None:
    route = respx.get(URL).respond(200, json=real_response)
    res = geocode.search(session, "Trg bana Jelačića, Zagreb", settings=settings)
    params = dict(route.calls.last.request.url.params)
    assert params == {
        "q": "Trg bana Jelačića, Zagreb",
        "format": "jsonv2",
        "countrycodes": "hr",
        "addressdetails": "1",
        "limit": "5",
        "accept-language": "hr",
    }
    assert route.calls.last.request.headers["user-agent"].startswith("datathon-test/0.1 (+mailto:")
    assert res.attribution == "© OpenStreetMap contributors (Nominatim)"
    assert not res.from_cache
    assert res.results[0]["name"] == "Trg bana Josipa Jelačića"


@respx.mock
def test_second_call_is_served_from_cache(
    session: Session, settings: CoreSettings, real_response: list[dict[str, object]]
) -> None:
    route = respx.get(URL).respond(200, json=real_response)
    first = geocode.search(session, "Trg bana Jelačića, Zagreb", settings=settings)
    second = geocode.search(
        session, "  trg BANA   jelačića, zagreb ", settings=settings
    )  # same key
    assert route.call_count == 1
    assert second.from_cache
    assert second.results == first.results
    assert second.fetched_at == first.fetched_at  # original retrieval time is kept


@respx.mock
def test_expired_cache_entry_is_refreshed(
    session: Session, settings: CoreSettings, real_response: list[dict[str, object]]
) -> None:
    route = respx.get(URL).respond(200, json=real_response)
    geocode.search(session, "zagreb", settings=settings)
    row = session.get(geocode.GeocodeCache, "zagreb")
    assert row is not None
    row.fetched_at = datetime.now(UTC) - timedelta(days=31)
    session.commit()
    again = geocode.search(session, "zagreb", settings=settings)
    assert route.call_count == 2
    assert not again.from_cache
    assert (datetime.now(UTC) - again.fetched_at) < timedelta(minutes=1)


@respx.mock
def test_viewbox_bounded_and_cache_key(
    session: Session, settings: CoreSettings, real_response: list[dict[str, object]]
) -> None:
    route = respx.get(URL).respond(200, json=real_response)
    vb = (15.8, 45.7, 16.1, 45.9)
    geocode.search(session, "ilica", settings=settings, viewbox=vb, bounded=True)
    params = route.calls.last.request.url.params
    assert params["viewbox"] == "15.8,45.7,16.1,45.9"
    assert params["bounded"] == "1"
    # a different viewbox must not hit the same cache entry
    geocode.search(session, "ilica", settings=settings)
    assert route.call_count == 2
    assert "bounded" not in route.calls.last.request.url.params


def test_empty_query_rejected(session: Session, settings: CoreSettings) -> None:
    with pytest.raises(ValueError, match="empty"):
        geocode.search(session, "   ", settings=settings)


@respx.mock
def test_unexpected_payload_rejected_and_not_cached(
    session: Session, settings: CoreSettings
) -> None:
    respx.get(URL).respond(200, json={"error": "nope"})
    with pytest.raises(ValueError, match="unexpected"):
        geocode.search(session, "x", settings=settings)
    assert session.query(geocode.GeocodeCache).count() == 0


def test_normalize_query() -> None:
    assert geocode.normalize_query("  A  B ") == "a b"
    assert geocode.normalize_query("a", (1, 2, 3, 4), True) != geocode.normalize_query(
        "a", (1, 2, 3, 4), False
    )


def test_throttle_enforces_one_request_per_second(monkeypatch: pytest.MonkeyPatch) -> None:
    sleeps: list[float] = []
    clock = [1000.0]

    def fake_sleep(s: float) -> None:
        sleeps.append(s)
        clock[0] += s

    monkeypatch.setattr(
        geocode, "time", SimpleNamespace(monotonic=lambda: clock[0], sleep=fake_sleep)
    )
    monkeypatch.setattr(geocode, "_last_call", 0.0)
    _REAL_THROTTLE()
    _REAL_THROTTLE()
    assert sleeps == [pytest.approx(1.0)]
