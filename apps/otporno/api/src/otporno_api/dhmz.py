"""DHMZ current observations (P1): ``https://vrijeme.hr/hrvatska_n.xml``.

The file lists the latest hourly observation of every station. ``DatumTermin`` carries the date and the hour
of the observation, which is taken as Europe/Zagreb local time. Results are cached for 30 minutes and hidden
once they are older than 3 hours (a stale feed must not be shown as "now"). A humidity of exactly 0 is a
sensor gap in the feed (seen on 2026-11-04 for an automatic station) and is treated as missing.
"""

from __future__ import annotations

import threading
import time
import xml.etree.ElementTree as ET
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from otporno_api.heat import km_between

ZAGREB = ZoneInfo("Europe/Zagreb")
TTL_S = 30 * 60
MAX_AGE = timedelta(hours=3)
NEAREST_N = 3
MAX_KM = 60.0
ATTRIBUTION = "Izvor: Državni hidrometeorološki zavod (DHMZ), vrijeme.hr"


@dataclass(frozen=True)
class Station:
    """One station of the DHMZ feed."""

    name: str
    lat: float
    lon: float
    automatic: bool
    temp_c: float | None
    humidity_pct: float | None
    pressure_hpa: float | None
    wind_dir: str | None
    wind_ms: float | None
    condition: str | None


def _num(text: str | None) -> float | None:
    if text is None:
        return None
    s = text.strip().replace(",", ".")
    if s in ("", "-"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _txt(el: ET.Element, tag: str) -> str | None:
    value = el.findtext(tag)
    if value is None:
        return None
    value = value.strip()
    return None if value in ("", "-") else value


def parse(xml: str | bytes) -> tuple[datetime, list[Station]]:
    """Observation time (timezone-aware) and the stations of the feed."""
    root = ET.fromstring(xml)  # noqa: S314 (public DHMZ feed fetched from a fixed URL)
    date = (root.findtext("DatumTermin/Datum") or "").strip()
    hour = int((root.findtext("DatumTermin/Termin") or "0").strip())
    observed = datetime.strptime(date, "%d.%m.%Y").replace(hour=hour, tzinfo=ZAGREB)
    stations: list[Station] = []
    for g in root.iter("Grad"):
        lat, lon = _num(g.findtext("Lat")), _num(g.findtext("Lon"))
        name = _txt(g, "GradIme")
        d = g.find("Podatci")
        if lat is None or lon is None or not name or d is None:
            continue
        humidity = _num(d.findtext("Vlaga"))
        stations.append(
            Station(
                name=name,
                lat=lat,
                lon=lon,
                automatic=g.get("autom") == "1",
                temp_c=_num(d.findtext("Temp")),
                humidity_pct=None if humidity in (None, 0.0) else humidity,
                pressure_hpa=_num(d.findtext("Tlak")),
                wind_dir=_txt(d, "VjetarSmjer"),
                wind_ms=_num(d.findtext("VjetarBrzina")),
                condition=_txt(d, "Vrijeme"),
            )
        )
    return observed, stations


def nearest(
    stations: list[Station], lat: float, lon: float, n: int = NEAREST_N
) -> list[dict[str, Any]]:
    """The ``n`` closest stations within ``MAX_KM`` as dicts with ``distance_km``."""
    scored = sorted(((km_between(lat, lon, s.lat, s.lon), s) for s in stations), key=lambda t: t[0])
    return [{**asdict(s), "distance_km": round(d, 1)} for d, s in scored[:n] if d <= MAX_KM]


class DhmzLive:
    """Thread-safe 30-minute cache over a fetch function returning the feed text."""

    def __init__(
        self,
        fetch: Callable[[], str | bytes],
        clock: Callable[[], float] = time.time,
    ) -> None:
        self._fetch = fetch
        self._clock = clock
        self._lock = threading.Lock()
        self._at = 0.0
        self._data: tuple[datetime, list[Station]] | None = None

    def get(self) -> tuple[datetime, list[Station], datetime]:
        """``(observed_at, stations, fetched_at)``; refetches when the cache is older than 30 minutes."""
        with self._lock:
            now = self._clock()
            if self._data is None or now - self._at > TTL_S:
                self._data = parse(self._fetch())
                self._at = now
            observed, stations = self._data
            return observed, stations, datetime.fromtimestamp(self._at, UTC)


def payload(
    live: DhmzLive, lat: float | None, lon: float | None, now: datetime | None = None
) -> dict[str, Any]:
    """Body of ``GET /live/dhmz``: stations (nearest to the point when given), or ``stale`` when too old."""
    observed, stations, fetched = live.get()
    now = now or datetime.now(UTC)
    age = now - observed
    base: dict[str, Any] = {
        "observed_at": observed.isoformat(),
        "fetched_at": fetched.isoformat(),
        "age_minutes": round(age.total_seconds() / 60),
        "attribution": ATTRIBUTION,
    }
    if age > MAX_AGE:
        return {
            **base,
            "status": "stale",
            "message": "Podaci DHMZ-a stariji su od 3 sata i zato se ne prikazuju.",
            "stations": [],
        }
    chosen = (
        nearest(stations, lat, lon)
        if lat is not None and lon is not None
        else [{**asdict(s), "distance_km": None} for s in stations]
    )
    return {**base, "status": "ok", "message": None, "stations": chosen}
