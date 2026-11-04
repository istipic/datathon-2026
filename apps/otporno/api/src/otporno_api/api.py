"""HTTP API of Otporko (all routes under /api/v1)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Query, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import text
from sqlalchemy.orm import Session, sessionmaker

from opendata_core import geocode as core_geocode
from opendata_core import http as http_mod
from otporno_api import brief as brief_mod
from otporno_api import cooling, dhmz, exposure
from otporno_api.compute import run_compute
from otporno_api.constants import BAND_EDGES, DEFAULT_WEIGHTS
from otporno_api.fire import FireCache
from otporno_api.om_client import OpenMeteoClient
from otporno_api.passport import OutsideCroatia, build_passport
from otporno_api.priority import WeightError
from otporno_api.settings import OtpornoSettings

Lat = Annotated[float, Query(description="WGS84 latitude")]
Lon = Annotated[float, Query(description="WGS84 longitude")]


class CoolingRequest(BaseModel):
    """Body of ``POST /cooling-centres``."""

    model_config = {"extra": "forbid"}

    lau_id: str = Field(min_length=3, max_length=16)
    k: int = Field(ge=1, le=5)
    min_band: Literal["niska", "umjerena", "visoka"] = Field(
        default="visoka",
        description="Lowest heat band whose 65+ residents count as demand (default: visoka and above)",
    )


def geocode_title(result: dict[str, Any]) -> str:
    """Short title of a Nominatim result: "Ilica 200", else the place name."""
    address = result.get("address") or {}
    road = next(
        (address[k] for k in ("road", "pedestrian", "footway", "path") if address.get(k)), None
    )
    if road:
        number = address.get("house_number")
        return f"{road} {number}" if number else str(road)
    return str(result.get("name") or str(result.get("display_name", "")).split(",")[0].strip())


def make_router(
    get_session: Callable[..., Any],
    settings: OtpornoSettings,
    factory: sessionmaker[Session],
    dhmz_live: dhmz.DhmzLive | None = None,
) -> APIRouter:
    """Routes bound to the settings and the session factory."""
    router = APIRouter(prefix="/api/v1")
    fire_cache = FireCache()

    def known(session: Session, lau_id: str) -> None:
        if exposure.municipality_info(session, lau_id) is None:
            raise HTTPException(404, "Nepoznata općina ili grad.")

    @router.get("/geocode")
    def geocode(
        q: Annotated[str, Query(min_length=3, max_length=120)],
        session: Session = Depends(get_session),  # noqa: B008
    ) -> dict[str, Any]:
        """Address search anywhere in Croatia (OpenStreetMap Nominatim, cached 30 days)."""
        try:
            result = core_geocode.search(session, q, settings=settings)
        except Exception as exc:
            raise HTTPException(502, "Usluga za pretragu adresa trenutno nije dostupna.") from exc
        items: list[dict[str, Any]] = []
        seen: set[tuple[str, float, float]] = set()
        for r in result.results:
            item = {
                "label": r.get("display_name", ""),
                "title": geocode_title(r),
                "lat": float(r["lat"]),
                "lon": float(r["lon"]),
                "type": r.get("type"),
            }
            key = (item["title"], round(item["lat"], 4), round(item["lon"], 4))
            if key not in seen:
                seen.add(key)
                items.append(item)
        return {"results": items, "attribution": result.attribution, "cached": result.from_cache}

    @router.get("/passport")
    def passport(
        lat: Lat,
        lon: Lon,
        session: Session = Depends(get_session),  # noqa: B008
    ) -> dict[str, Any]:
        """Risk passport of a point: flood, heat today vs 2031-2050, cited actions."""

        def client() -> OpenMeteoClient:
            return OpenMeteoClient(settings, factory, interactive=True)

        try:
            return build_passport(session, settings, lat, lon, client, fire_cache)
        except OutsideCroatia as exc:
            raise HTTPException(422, str(exc)) from exc

    @router.get("/municipalities")
    def municipalities(
        q: Annotated[str, Query(min_length=2, max_length=80)],
        session: Session = Depends(get_session),  # noqa: B008
    ) -> dict[str, Any]:
        """Municipality search by name."""
        return {"results": exposure.search_municipalities(session, q)}

    @router.get("/municipalities/{lau_id}/exposure")
    def municipality_exposure(
        lau_id: str, session: Session = Depends(get_session)
    ) -> dict[str, Any]:  # noqa: B008
        """People and 65+ per hazard and band; ``status`` is ready | computing | unavailable."""
        data = exposure.exposure(session, lau_id)
        if data is None:
            raise HTTPException(404, "Nepoznata općina ili grad.")
        heat_ready = data["hazards"]["heat"]["status"] == "ready"
        raw = data["status"]
        if raw in ("ready", "computing"):
            data["status"] = raw
        else:
            data["status"] = "ready" if heat_ready and raw == "not_started" else "unavailable"
        data["can_compute"] = data["status"] != "computing"
        data["reason"] = raw if data["status"] == "unavailable" else None
        return data

    @router.post("/municipalities/{lau_id}/compute", status_code=202)
    def compute(
        lau_id: str,
        tasks: BackgroundTasks,
        response: Response,
        session: Session = Depends(get_session),  # noqa: B008
    ) -> dict[str, Any]:
        """Start (idempotently) the computation for a municipality; poll ``/exposure`` for the result."""
        known(session, lau_id)
        state = exposure.get_status(session, lau_id)
        if state["status"] in ("computing", "ready"):
            response.status_code = 200 if state["status"] == "ready" else 202
            return {"lau_id": lau_id, "status": state["status"], "started": False}
        exposure.set_status(session, lau_id, "computing", "Izračun je u tijeku.")
        tasks.add_task(run_compute, factory, settings, lau_id)
        return {"lau_id": lau_id, "status": "computing", "started": True}

    @router.get("/cells")
    def cells(
        lau: Annotated[str, Query(min_length=3, max_length=16)],
        w_flood: Annotated[float, Query(ge=0, le=1)] = DEFAULT_WEIGHTS["flood"],
        w_heat: Annotated[float, Query(ge=0, le=1)] = DEFAULT_WEIGHTS["heat"],
        w_fire: Annotated[float, Query(ge=0, le=1)] = DEFAULT_WEIGHTS["fire"],
        session: Session = Depends(get_session),  # noqa: B008
    ) -> dict[str, Any]:
        """Inhabited 1 km cells with hazard scores and priority (GeoJSON); weights must sum to 1 ± 0.01."""
        try:
            data = exposure.cells_geojson(
                session, lau, {"flood": w_flood, "heat": w_heat, "fire": w_fire}
            )
        except WeightError as exc:
            raise HTTPException(422, str(exc)) from exc
        if data is None:
            raise HTTPException(404, "Nepoznata općina ili grad.")
        return data

    @router.post("/cooling-centres")
    def cooling_centres(
        body: CoolingRequest, session: Session = Depends(get_session)
    ) -> dict[str, Any]:  # noqa: B008
        """Proposed cooling-centre sites (public buildings) that cover most 65+ residents in hot cells."""
        known(session, body.lau_id)
        edge = {"niska": 0.0, "umjerena": BAND_EDGES[0], "visoka": BAND_EDGES[1]}[body.min_band]
        problem = cooling.load_problem(session, body.lau_id, edge)
        if len(problem.demand) == 0:
            raise HTTPException(
                409,
                f"Nema ćelija u pojasu toplinskog rizika „{body.min_band}” ili višem sa stanovnicima 65+ za ovu općinu "
                "(izračun nije gotov, nema podataka ili je rizik niži). Probajte uključiti niži pojas.",
            )
        if not problem.sites:
            raise HTTPException(409, "Nema učitanih javnih zgrada kao kandidata za ovu općinu.")
        result = cooling.propose(problem, body.k)
        result["lau_id"] = body.lau_id
        result["k"] = body.k
        result["min_band"] = body.min_band
        result["note"] = (
            "Pokrivenost je zračna udaljenost 415 m (10 min hoda pri 0,9 m/s uz faktor zaobilaska 1,3); "
            "postojeći centri za rashlađivanje nisu uključeni jer ne postoji javni registar."
        )
        return result

    @router.get("/health/climate-quota")
    def climate_quota(session: Session = Depends(get_session)) -> dict[str, Any]:  # noqa: B008
        """How much of the Open-Meteo free tier is used (last 24 h) and how many points are cached."""
        used = session.execute(
            text(
                "select coalesce(sum(cost), 0) c, count(*) n from api_call_log where service = 'open-meteo-climate' and called_at > now() - interval '24 hours'"
            )
        ).one()
        pts = session.execute(
            text("select count(distinct (lat_r, lon_r)) from heat_point")
        ).scalar_one()
        return {
            "cost_24h": round(float(used.c)),
            "calls_24h": int(used.n),
            "daily_limit": 10000,
            "points_cached": int(pts),
        }

    def fetch_dhmz() -> bytes:
        with http_mod.make_client(settings) as client:
            response = client.get(settings.dhmz_url)
            response.raise_for_status()
            return response.content

    live = dhmz_live or dhmz.DhmzLive(fetch_dhmz)

    @router.get("/live/dhmz")
    def live_dhmz(
        lat: Annotated[float | None, Query()] = None,
        lon: Annotated[float | None, Query()] = None,
    ) -> dict[str, Any]:
        """Latest DHMZ observations (cached 30 min, hidden when older than 3 h); nearest stations when a point is given."""
        if (lat is None) != (lon is None):
            raise HTTPException(422, "Navedite i lat i lon.")
        try:
            return dhmz.payload(live, lat, lon)
        except Exception as exc:
            raise HTTPException(502, "Podaci DHMZ-a trenutno nisu dostupni.") from exc

    @router.get("/municipalities/{lau_id}/brief", response_class=HTMLResponse)
    def municipality_brief(lau_id: str, session: Session = Depends(get_session)) -> HTMLResponse:  # noqa: B008
        """Printable HTML brief of a municipality (exposure, priority cells, cited measures)."""
        html = brief_mod.build_brief(session, lau_id)
        if html is None:
            raise HTTPException(404, "Nepoznata općina ili grad.")
        return HTMLResponse(html)

    return router
