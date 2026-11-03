"""GTFS frequency logic on a trimmed REAL ZET feed (recorded 2026-11-03, routes 1, 2, 34)."""

from __future__ import annotations

import csv
import io
import zipfile
from collections import Counter
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from blizu_api.ingest import gtfs

FIXTURE = Path(__file__).parent / "fixtures" / "zet-gtfs" / "2026-11-03_zet_gtfs_3routes.zip"


@pytest.fixture(scope="module")
def feed() -> gtfs.Feed:
    return gtfs.read_feed(FIXTURE)


def test_feed_date_comes_from_feed_info(feed: gtfs.Feed) -> None:
    assert gtfs.feed_date(feed) == "2026-10-21"


def test_reference_date_is_first_active_wednesday(feed: gtfs.Feed) -> None:
    # 2026-11-03 is a Tuesday -> the next day, Wednesday 2026-11-04
    assert gtfs.choose_reference_date(
        date(2026, 11, 3), feed.calendar, feed.calendar_dates
    ) == date(2026, 11, 4)
    # a Wednesday maps to itself
    assert gtfs.choose_reference_date(
        date(2026, 11, 4), feed.calendar, feed.calendar_dates
    ) == date(2026, 11, 4)
    # Thursday -> the following Wednesday
    assert gtfs.choose_reference_date(
        date(2026, 11, 5), feed.calendar, feed.calendar_dates
    ) == date(2026, 11, 11)


def test_reference_date_outside_feed_coverage_fails(feed: gtfs.Feed) -> None:
    with pytest.raises(ValueError, match="no Wednesday"):
        gtfs.choose_reference_date(
            date(2031, 1, 1), feed.calendar, feed.calendar_dates, horizon_weeks=3
        )


def test_active_services_use_calendar_dates_when_calendar_is_all_zero(feed: gtfs.Feed) -> None:
    # the real feed has weekday flags 0 everywhere; service days come from calendar_dates.txt only
    assert not (feed.calendar[list(gtfs.WEEKDAYS)] == "1").any().any()
    assert gtfs.active_services(date(2026, 11, 4), feed.calendar, feed.calendar_dates) == {"0_1"}
    assert gtfs.active_services(date(2027, 6, 1), feed.calendar, feed.calendar_dates) == set()


def test_active_services_calendar_and_exceptions() -> None:
    calendar = pd.DataFrame(
        [
            {
                "service_id": "wk",
                "monday": "1",
                "tuesday": "1",
                "wednesday": "1",
                "thursday": "1",
                "friday": "1",
                "saturday": "0",
                "sunday": "0",
                "start_date": "20260101",
                "end_date": "20261231",
            }
        ]
    )
    exceptions = pd.DataFrame(
        [
            {
                "service_id": "wk",
                "date": "20260107",
                "exception_type": "2",
            },  # removed on a Wednesday
            {
                "service_id": "extra",
                "date": "20260110",
                "exception_type": "1",
            },  # added on a Saturday
        ]
    )
    assert gtfs.active_services(date(2026, 1, 14), calendar, exceptions) == {"wk"}
    assert gtfs.active_services(date(2026, 1, 7), calendar, exceptions) == set()
    assert gtfs.active_services(date(2026, 1, 10), calendar, exceptions) == {"extra"}
    assert gtfs.active_services(date(2027, 1, 13), calendar, exceptions) == set()  # out of range


def _independent_counts(ref: str) -> Counter[str]:
    """Departures 07:00-09:00 per station, counted with plain csv (no pandas) as a cross-check."""
    with zipfile.ZipFile(FIXTURE) as z:

        def rows(name: str) -> list[dict[str, str]]:
            return list(csv.DictReader(io.TextIOWrapper(z.open(name), encoding="utf-8")))

        services = {
            r["service_id"]
            for r in rows("calendar_dates.txt")
            if r["date"] == ref and r["exception_type"] == "1"
        }
        trips = {r["trip_id"] for r in rows("trips.txt") if r["service_id"] in services}
        parent = {r["stop_id"]: r["parent_station"] or r["stop_id"] for r in rows("stops.txt")}
        by_trip: dict[str, list[dict[str, str]]] = {}
        for r in rows("stop_times.txt"):
            if r["trip_id"] in trips:
                by_trip.setdefault(r["trip_id"], []).append(r)
    counts: Counter[str] = Counter()
    for stops in by_trip.values():
        stops.sort(key=lambda r: int(r["stop_sequence"]))
        for r in stops[:-1]:  # the last stop of a trip has no departure
            if "07:00:00" <= r["departure_time"] < "09:00:00":
                counts[parent[r["stop_id"]]] += 1
    return counts


def test_frequencies_match_an_independent_count(feed: gtfs.Feed) -> None:
    freq = gtfs.stop_frequencies(feed, date(2026, 11, 4))
    expected = _independent_counts("20261104")
    assert len(freq) == len(expected) > 20
    got = dict(
        zip(freq["stop_id"], freq["dep_per_hour"] * 2, strict=True)
    )  # back to departures in 2 h
    assert got == {k: float(v) for k, v in expected.items()}


def test_frequency_is_departures_divided_by_two_hours(feed: gtfs.Feed) -> None:
    freq = gtfs.stop_frequencies(feed, date(2026, 11, 4))
    busiest = freq.sort_values("dep_per_hour", ascending=False).iloc[0]
    expected = _independent_counts("20261104")
    assert busiest["dep_per_hour"] == max(expected.values()) / 2
    assert gtfs.MIN_DEP_PER_HOUR == 6.0
    assert (freq["dep_per_hour"] >= 6).any()  # trams in the morning peak run several times an hour


def test_stations_use_parent_coordinates_and_zagreb_extent(feed: gtfs.Feed) -> None:
    freq = gtfs.stop_frequencies(feed, date(2026, 11, 4))
    assert freq["lat"].between(45.6, 46.0).all()
    assert freq["lon"].between(15.7, 16.3).all()
    parents = feed.stops[feed.stops["location_type"] == "1"].set_index("stop_id")
    sample = freq[freq["stop_id"].isin(parents.index)].iloc[0]
    assert sample["lat"] == pytest.approx(float(parents.loc[sample["stop_id"], "stop_lat"]))
    assert sample["name"] == parents.loc[sample["stop_id"], "stop_name"]


def test_no_service_on_inactive_day_gives_no_frequencies(feed: gtfs.Feed) -> None:
    assert gtfs.stop_frequencies(feed, date(2027, 6, 2)).empty
