"""ZET GTFS: morning-peak departures per hour per stop (aggregated to parent stations)."""

from __future__ import annotations

import zipfile
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path

import pandas as pd
import structlog
from sqlalchemy import delete, insert
from sqlalchemy.orm import Session

from blizu_api.constants import SRC_GTFS
from blizu_api.db import Facility, GtfsStopFrequency
from blizu_api.manifest import Manifest, sha256_file
from blizu_api.settings import BlizuSettings
from opendata_core import http as http_mod
from opendata_core.provenance import record_ingestion

log = structlog.get_logger(__name__)

GTFS_URL = "https://zet.hr/gtfs-scheduled/latest"
WINDOW_START = "07:00:00"
WINDOW_END = "09:00:00"
WINDOW_HOURS = 2.0
MIN_DEP_PER_HOUR = 6.0  # a stop counts as public transport access from this frequency
WEEKDAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


@dataclass(frozen=True)
class Feed:
    """The GTFS tables Blizu needs."""

    stops: pd.DataFrame
    trips: pd.DataFrame
    stop_times: pd.DataFrame
    calendar: pd.DataFrame
    calendar_dates: pd.DataFrame
    feed_info: pd.DataFrame


def read_feed(path: Path) -> Feed:
    """Read the needed files from a GTFS zip (strings only; ids must keep their text form)."""
    with zipfile.ZipFile(path) as z:

        def read(name: str, **kw: object) -> pd.DataFrame:
            if name not in z.namelist():
                return pd.DataFrame()
            with z.open(name) as fh:
                return pd.read_csv(fh, dtype=str, **kw)  # type: ignore[call-overload, no-any-return]

        return Feed(
            stops=read("stops.txt"),
            trips=read("trips.txt", usecols=["route_id", "service_id", "trip_id"]),
            stop_times=read(
                "stop_times.txt",
                usecols=lambda c: (
                    c in {"trip_id", "departure_time", "stop_id", "stop_sequence", "pickup_type"}
                ),
            ),
            calendar=read("calendar.txt"),
            calendar_dates=read("calendar_dates.txt"),
            feed_info=read("feed_info.txt"),
        )


def active_services(day: date, calendar: pd.DataFrame, calendar_dates: pd.DataFrame) -> set[str]:
    """service_ids running on ``day`` (calendar.txt weekday flags + calendar_dates.txt exceptions)."""
    ymd = day.strftime("%Y%m%d")
    active: set[str] = set()
    if not calendar.empty:
        weekday = WEEKDAYS[day.weekday()]
        in_range = (calendar["start_date"] <= ymd) & (calendar["end_date"] >= ymd)
        active |= set(calendar.loc[in_range & (calendar[weekday] == "1"), "service_id"])
    if not calendar_dates.empty:
        today = calendar_dates[calendar_dates["date"] == ymd]
        active |= set(today.loc[today["exception_type"] == "1", "service_id"])
        active -= set(today.loc[today["exception_type"] == "2", "service_id"])
    return active


def choose_reference_date(
    today: date, calendar: pd.DataFrame, calendar_dates: pd.DataFrame, horizon_weeks: int = 12
) -> date:
    """First Wednesday on or after ``today`` that has at least one active service."""
    day = today + timedelta(days=(2 - today.weekday()) % 7)  # Monday=0 -> Wednesday=2
    for _ in range(horizon_weeks):
        if active_services(day, calendar, calendar_dates):
            return day
        day += timedelta(days=7)
    raise ValueError(f"no Wednesday with active service within {horizon_weeks} weeks of {today}")


def stop_frequencies(feed: Feed, ref_day: date) -> pd.DataFrame:
    """Departures per hour in 07:00-09:00 of ``ref_day`` per stop (parent station when present).

    Excludes the final stop of every trip (no departure there) and stops with pickup_type=1.
    Columns: stop_id, name, lat, lon, dep_per_hour.
    """
    services = active_services(ref_day, feed.calendar, feed.calendar_dates)
    trips = feed.trips[feed.trips["service_id"].isin(services)]["trip_id"]
    st = feed.stop_times[feed.stop_times["trip_id"].isin(set(trips))].copy()
    st["seq"] = st["stop_sequence"].astype(int)
    last_seq = st.groupby("trip_id")["seq"].transform("max")
    st = st[st["seq"] < last_seq]
    if "pickup_type" in st.columns:
        st = st[st["pickup_type"].fillna("0") != "1"]
    window = st[(st["departure_time"] >= WINDOW_START) & (st["departure_time"] < WINDOW_END)]

    stops = feed.stops.set_index("stop_id")
    parent = stops["parent_station"].reindex(window["stop_id"]).to_numpy()
    station = pd.Series(parent, index=window.index).fillna(window["stop_id"])
    counts = station.value_counts().rename("departures").rename_axis("station_id").reset_index()

    def coords(station_id: str) -> tuple[str, float, float]:
        if station_id in stops.index and stops.loc[station_id, "location_type"] == "1":
            row = stops.loc[station_id]
            return row["stop_name"], float(row["stop_lat"]), float(row["stop_lon"])
        children = feed.stops[
            (feed.stops["stop_id"] == station_id) | (feed.stops["parent_station"] == station_id)
        ]
        return (
            children["stop_name"].iloc[0],
            float(children["stop_lat"].astype(float).mean()),
            float(children["stop_lon"].astype(float).mean()),
        )

    rows = []
    for r in counts.itertuples(index=False):
        name, lat, lon = coords(str(r.station_id))
        rows.append(
            {
                "stop_id": str(r.station_id),
                "name": name,
                "lat": lat,
                "lon": lon,
                "dep_per_hour": r.departures / WINDOW_HOURS,
            }
        )
    return pd.DataFrame(rows, columns=["stop_id", "name", "lat", "lon", "dep_per_hour"])


def feed_date(feed: Feed) -> str:
    """ISO date of the feed (feed_start_date from feed_info.txt)."""
    raw = feed.feed_info["feed_start_date"].iloc[0]
    return f"{raw[:4]}-{raw[4:6]}-{raw[6:8]}"


def ingest_gtfs(session: Session, settings: BlizuSettings) -> pd.DataFrame:
    """``blizu ingest gtfs``: download, compute frequencies, store stops and prijevoz facilities."""
    today = datetime.now(UTC).date()
    zip_path = settings.raw_dir / f"{today.isoformat()}_zet-gtfs.zip"
    with (
        http_mod.make_client(settings) as client,
        record_ingestion(session, SRC_GTFS, GTFS_URL) as run,
    ):
        head = client.head(GTFS_URL)
        modified = head.headers.get("Last-Modified")
        _, sha = http_mod.download_file(client, GTFS_URL, zip_path)
        feed = read_feed(zip_path)
        ref_day = choose_reference_date(today, feed.calendar, feed.calendar_dates)
        freq = stop_frequencies(feed, ref_day)
        fdate = feed_date(feed)
        run.sha256 = sha
        run.source_last_modified = parsedate_to_datetime(modified) if modified else None
        log.info("gtfs_frequencies", ref_date=str(ref_day), stops=len(freq), feed_date=fdate)

        session.execute(delete(Facility).where(Facility.source_id == SRC_GTFS))
        session.execute(delete(GtfsStopFrequency))
        point = lambda r: f"SRID=4326;POINT({r.lon:.7f} {r.lat:.7f})"  # noqa: E731
        session.execute(
            insert(GtfsStopFrequency),
            [
                {
                    "stop_id": r.stop_id,
                    "name": r.name,
                    "geom": point(r),
                    "dep_per_hour": float(r.dep_per_hour),
                    "ref_date": ref_day.isoformat(),
                    "feed_date": fdate,
                }
                for r in freq.itertuples(index=False)
            ],
        )
        good = freq[freq["dep_per_hour"] >= MIN_DEP_PER_HOUR]
        session.execute(
            insert(Facility),
            [
                {
                    "category": "prijevoz",
                    "name": r.name,
                    "address": None,
                    "geom": point(r),
                    "source_id": SRC_GTFS,
                    "tier": "official",
                    "source_record_id": r.stop_id,
                    "attrs": {
                        "dep_per_hour": float(r.dep_per_hour),
                        "ref_date": ref_day.isoformat(),
                    },
                }
                for r in good.itertuples(index=False)
            ],
        )
        run.rows = len(freq)
    Manifest(settings.derived_dir).set(
        "gtfs",
        ref_date=ref_day.isoformat(),
        feed_date=fdate,
        sha256=sha,
        stops=len(freq),
        prijevoz_facilities=len(good),
        raw=zip_path.name,
        zip_sha256=sha256_file(zip_path),
    )
    return freq
