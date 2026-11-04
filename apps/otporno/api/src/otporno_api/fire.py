"""Wildfire exposure from CORINE Land Cover 2018 (P1).

The EEA map service answers point queries (``identify``) with the official CORINE code, so nothing is
downloaded: for an address two queries are made, the class *at the point* and the classes within about 500 m.
This is a **land-cover exposure** (is natural vegetation, CORINE 311-324, at or next to the address?), not a
fire probability; CORINE maps polygons of at least 25 ha, so the confidence is always low.

  inside 311-324                          -> visoka    (score 0.65)
  not inside, but 311-324 within ~500 m   -> umjerena  (score 0.40)
  otherwise                               -> niska     (score 0.10)
"""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from typing import Any

import httpx

from opendata_core import http as http_mod
from otporno_api.settings import OtpornoSettings

VEGETATION = {
    311: "Bjelogorična šuma",
    312: "Crnogorična šuma",
    313: "Mješovita šuma",
    321: "Prirodni travnjaci",
    322: "Vrištine i grmolike formacije",
    323: "Sklerofilna vegetacija (makija)",
    324: "Prijelazno područje šuma–grmlje",
}
SCORES = {"niska": 0.10, "umjerena": 0.40, "visoka": 0.65}
NEIGHBOURHOOD_M = 500.0
IDENTIFY_PATH = "/identify"
CACHE_TTL_S = 24 * 3600
ATTRIBUTION = "Copernicus Land Monitoring Service, CORINE Land Cover 2018 (© EEA)"
METHOD = (
    "Izloženost vegetaciji prema CORINE Land Cover 2018: nalazi li se prirodna vegetacija (šume, travnjaci, "
    "makija; klase 311–324) na adresi ili unutar oko 500 m. To nije vjerojatnost požara; najmanja kartirana "
    "površina je 25 ha."
)


@dataclass(frozen=True)
class FireResult:
    """Fire exposure of one point."""

    band: str
    score: float
    code_at_point: int | None
    label_at_point: str | None
    vegetation_nearby: dict[int, str]


def _codes(data: dict[str, Any], layer_id: int | None = None) -> list[int]:
    out = []
    for r in data.get("results", []):
        if layer_id is not None and r.get("layerId") != layer_id:
            continue
        code = (r.get("attributes") or {}).get("Code_18") or (r.get("attributes") or {}).get(
            "Raster.CODE_18"
        )
        if code and str(code).isdigit():
            out.append(int(code))
    return out


def classify(point: dict[str, Any], around: dict[str, Any]) -> FireResult:
    """Band from the two identify responses (pure function, tested on recorded responses)."""
    at = _codes(point, 0)
    code = at[0] if at else None
    label = None
    for r in point.get("results", []):
        if r.get("layerId") == 1:
            label = (r.get("attributes") or {}).get("Raster.LABEL3")
    nearby = {c: VEGETATION[c] for c in sorted(set(_codes(around, 0))) if c in VEGETATION}
    if code in VEGETATION:
        band = "visoka"
        label = VEGETATION[code]
    elif nearby:
        band = "umjerena"
    else:
        band = "niska"
    return FireResult(band, SCORES[band], code, label, nearby)


def _extent(lon: float, lat: float, half_deg_lat: float) -> str:
    import math

    half_lon = half_deg_lat / math.cos(math.radians(lat))
    return f"{lon - half_lon},{lat - half_deg_lat},{lon + half_lon},{lat + half_deg_lat}"


def fetch(settings: OtpornoSettings, lon: float, lat: float, client: httpx.Client) -> FireResult:
    """Two identify calls against the EEA service."""
    base = settings.corine_url.rstrip("/") + IDENTIFY_PATH
    common = {
        "geometry": f"{lon},{lat}",
        "geometryType": "esriGeometryPoint",
        "sr": "4326",
        "returnGeometry": "false",
        "f": "json",
        "imageDisplay": "400,400,96",
    }
    point = client.get(
        base,
        params={**common, "layers": "all", "tolerance": "1", "mapExtent": _extent(lon, lat, 0.01)},
    )
    point.raise_for_status()
    # 400 px over 0.04 degrees of latitude (~4.4 km) is ~11 m per pixel: 45 px ~ 500 m
    around = client.get(
        base,
        params={
            **common,
            "layers": "all:0",
            "tolerance": "45",
            "mapExtent": _extent(lon, lat, 0.02),
        },
    )
    around.raise_for_status()
    return classify(point.json(), around.json())


class FireCache:
    """24-hour in-process cache keyed by the point rounded to ~10 m."""

    def __init__(self, clock: Any = time.time) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._items: dict[tuple[float, float], tuple[float, FireResult]] = {}

    def get_or_fetch(
        self, settings: OtpornoSettings, lon: float, lat: float, client: httpx.Client | None = None
    ) -> FireResult:
        key = (round(lon, 4), round(lat, 4))
        with self._lock:
            hit = self._items.get(key)
            if hit and self._clock() - hit[0] < CACHE_TTL_S:
                return hit[1]
        own = client is None
        client = client or http_mod.make_client(settings)
        try:
            result = fetch(settings, lon, lat, client)
        finally:
            if own:
                client.close()
        with self._lock:
            self._items[key] = (self._clock(), result)
        return result


def payload(result: FireResult) -> dict[str, Any]:
    """The ``fire`` object of ``GET /passport``."""
    return {
        "status": "ready",
        "band": result.band,
        "score": result.score,
        "land_cover": {"code": result.code_at_point, "label": result.label_at_point},
        "vegetation_nearby": [{"code": c, "label": n} for c, n in result.vegetation_nearby.items()],
        "radius_m": NEIGHBOURHOOD_M,
        "confidence": "niska",
        "confidence_reasons": ["CORINE kartira površine od najmanje 25 ha"],
        "method": METHOD,
        "attribution": ATTRIBUTION,
        "message": None,
    }
