"""The household Risk Passport of one address."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

import structlog
from sqlalchemy.orm import Session

from opendata_core.geo import in_croatia
from otporno_api.actions import actions_for
from otporno_api.constants import FLOOD_DISCLAIMER, MODELS, SRC_HV_FLOOD, SRC_OPEN_METEO
from otporno_api.exposure import municipality_of_point
from otporno_api.flood import flood_payload
from otporno_api.heat import (
    APPROX_MAX_KM,
    PointStats,
    band_of,
    fetch_full_point,
    grid_reference,
    nearest_full_point,
    percentile_of,
    point_rows,
    point_stats,
    round_coord,
)
from otporno_api.om_client import OpenMeteoClient, QuotaExceeded
from otporno_api.settings import OtpornoSettings

log = structlog.get_logger(__name__)

MIN_GRID_POINTS = 20  # below this the percentile reference is too thin to quote
GOOD_GRID_POINTS = 100
SPREAD_LIMIT = 0.5  # (max - min) / mean of the models' future hot days

ATTRIBUTION_HEAT = "Open-Meteo.com, CC BY 4.0 (klimatski modeli CMIP6, HighResMIP)"
HEAT_UNAVAILABLE = (
    "Procjena toplinskog rizika za ovu točku trenutno nije dostupna: dnevna kvota usluge Open-Meteo je "
    "iskorištena. Pokušajte ponovno kasnije."
)
NO_REFERENCE = "Nacionalna usporedna mreža još se puni (ograničenje usluge Open-Meteo); rizik nije moguće rangirati."


class OutsideCroatia(ValueError):
    """The point is not in Croatia."""


def heat_confidence(
    stats: PointStats, approximate: bool, grid_points: int
) -> tuple[str, list[str]]:
    """Confidence level (visoka/srednja/niska) and the reasons that lower it."""
    reasons: list[str] = []
    level = 2
    if len(stats.models) < len(MODELS):
        reasons.append(f"dostupno je {len(stats.models)} od {len(MODELS)} klimatskih modela")
        level = min(level, 1 if len(stats.models) >= 2 else 0)
    spread = (stats.fut_max - stats.fut_min) / stats.fut_mean if stats.fut_mean > 0 else 0.0
    if spread > SPREAD_LIMIT:
        reasons.append("modeli se međusobno znatno razlikuju")
        level = min(level, 1)
    if approximate:
        reasons.append("korištena je najbliža modelska točka (do 25 km)")
        level = min(level, 1)
    if grid_points < GOOD_GRID_POINTS:
        reasons.append(f"usporedna mreža ima {grid_points} točaka (cilj je cijela Hrvatska)")
        level = min(level, 1)
    return ("niska", "srednja", "visoka")[level], reasons


def _heat_block(
    session: Session,
    settings: OtpornoSettings,
    client_factory: Callable[[], OpenMeteoClient] | None,
    lat: float,
    lon: float,
) -> dict[str, Any]:
    key = (round_coord(lat), round_coord(lon))
    stats = point_stats(point_rows(session, *key))
    used = (key[0], key[1])
    approximate = False
    distance_km = 0.0
    quota_hit = False
    if stats is None and client_factory is not None:
        client = client_factory()
        try:
            fetch_full_point(client, session, key[0], key[1], batch=False, combined=True)
        except QuotaExceeded as exc:
            quota_hit = True
            log.warning("heat_quota", scope=exc.scope, retry_after=round(exc.retry_after))
        finally:
            client.close()
        stats = point_stats(point_rows(session, *key))
    if stats is None:
        near = nearest_full_point(session, *key)
        near_stats = point_stats(point_rows(session, near[0], near[1])) if near else None
        if near and near_stats:
            stats, used, approximate, distance_km = near_stats, (near[0], near[1]), True, near[2]
    if stats is None:
        return {
            "status": "unavailable",
            "message": HEAT_UNAVAILABLE
            if quota_hit
            else f"Nema klimatskih podataka za ovu točku (najbliža točka je dalja od {APPROX_MAX_KM:.0f} km).",
            "band": None,
            "score": None,
        }
    reference = grid_reference(session)
    grid_points = len(reference)
    pct = percentile_of(stats.fut_mean, reference) if grid_points >= MIN_GRID_POINTS else None
    confidence, reasons = heat_confidence(stats, approximate, grid_points)
    block: dict[str, Any] = {
        "status": "ready",
        "message": None if pct is not None else NO_REFERENCE,
        "band": band_of(pct),
        "score": None if pct is None else round(pct, 3),
        "percentile": None if pct is None else round(pct * 100),
        "base_hot_days": round(stats.base_mean, 1),
        "future_hot_days": {
            "mean": round(stats.fut_mean, 1),
            "min": round(stats.fut_min, 1),
            "max": round(stats.fut_max, 1),
        },
        "base_tropical_nights": None if stats.base_trop is None else round(stats.base_trop, 1),
        "future_tropical_nights": None if stats.fut_trop is None else round(stats.fut_trop, 1),
        "models": list(stats.models),
        "periods": {"base": "1991.–2020.", "future": "2031.–2050."},
        "thresholds": {"hot_day_tmax_c": 30, "tropical_night_tmin_c": 20},
        "model_point": {
            "lat": used[0],
            "lon": used[1],
            "approximate": approximate,
            "distance_km": round(distance_km, 1),
        },
        "grid_points": grid_points,
        "confidence": confidence,
        "confidence_reasons": reasons,
        "attribution": ATTRIBUTION_HEAT,
    }
    if quota_hit:
        block["note"] = (
            "Točka za ovu adresu nije mogla biti dohvaćena (kvota); prikazana je najbliža dostupna."
        )
    return block


def build_passport(
    session: Session,
    settings: OtpornoSettings,
    lat: float,
    lon: float,
    client_factory: Callable[[], OpenMeteoClient] | None = None,
) -> dict[str, Any]:
    """Flood + heat (+ fire placeholder) for a point in Croatia, with cited actions.

    Raises :class:`OutsideCroatia` for points outside the country.
    """
    if not in_croatia(lon, lat):
        raise OutsideCroatia("Točka nije unutar Hrvatske.")
    muni = municipality_of_point(session, lat, lon)
    if muni is None:
        raise OutsideCroatia("Točka nije unutar općine ili grada u Hrvatskoj.")
    flood = flood_payload(settings)
    heat = _heat_block(session, settings, client_factory, lat, lon)
    fire = {
        "status": "unavailable",
        "band": None,
        "message": "Procjena opasnosti od požara otvorenog prostora (P1) nije učitana.",
    }
    actions = {
        "flood": actions_for(
            session, "flood", None if flood["level"] is None else str(flood["band"] or "any")
        ),
        "heat": actions_for(session, "heat", heat.get("band")),
        "fire": [],
    }
    return {
        "location": {
            "lat": round(lat, 6),
            "lon": round(lon, 6),
            "municipality": muni,
        },
        "flood": flood,
        "heat": heat,
        "fire": fire,
        "actions": actions,
        "sources": [
            {
                "id": SRC_HV_FLOOD,
                "title": "Hrvatske vode – Karte opasnosti od poplava 2019.",
                "note": FLOOD_DISCLAIMER,
            },
            {"id": SRC_OPEN_METEO, "title": "Open-Meteo Climate API", "note": ATTRIBUTION_HEAT},
        ],
        "computed_at": datetime.now(UTC).isoformat(),
    }
