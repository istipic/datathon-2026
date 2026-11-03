"""HTTP API of Blizu (all routes under /api/v1)."""

from __future__ import annotations

from collections.abc import Callable
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from blizu_api import service
from blizu_api.constants import ZAGREB_VIEWBOX
from blizu_api.planner import Planner
from blizu_api.settings import BlizuSettings
from blizu_api.store import DataStore
from opendata_core import geocode as core_geocode
from opendata_core.geo import in_croatia

Persona = Literal["opce", "starija", "roditelj", "kolica"]
Category = Literal[
    "lijecnik", "ljekarna", "vrtic", "skola", "knjiznica", "posta", "prijevoz", "park", "namirnice"
]
Lat = Annotated[float, Query(ge=42.2, le=46.6, description="WGS84 latitude (Croatia)")]
Lon = Annotated[float, Query(ge=13.0, le=19.5, description="WGS84 longitude (Croatia)")]
MAX_FEATURES = 2000


class OptimiseRequest(BaseModel):
    """Body of ``POST /plan/optimise``."""

    model_config = {"extra": "forbid"}

    category: Category
    persona: Persona
    k: int = Field(ge=1, le=5)


def parse_latlon(value: str, name: str) -> tuple[float, float]:
    """Parse ``"lat,lon"`` and validate that it lies in Croatia."""
    try:
        lat_s, lon_s = value.split(",")
        lat, lon = float(lat_s), float(lon_s)
    except ValueError as exc:
        raise HTTPException(422, f"Parametar '{name}' mora biti oblika 'lat,lon'.") from exc
    if not in_croatia(lon, lat):
        raise HTTPException(422, f"Parametar '{name}' nije unutar Hrvatske.")
    return lat, lon


def parse_bbox(value: str) -> tuple[float, float, float, float]:
    """Parse ``minLon,minLat,maxLon,maxLat``."""
    try:
        parts = tuple(float(p) for p in value.split(","))
    except ValueError as exc:
        raise HTTPException(
            422, "Parametar 'bbox' mora biti 'minLon,minLat,maxLon,maxLat'."
        ) from exc
    if len(parts) != 4 or parts[0] >= parts[2] or parts[1] >= parts[3]:
        raise HTTPException(
            422, "Parametar 'bbox' mora biti 'minLon,minLat,maxLon,maxLat' (min < max)."
        )
    return parts  # type: ignore[return-value]


def get_store(request: Request) -> DataStore:
    """Dependency: the store loaded at start-up."""
    store = getattr(request.app.state, "store", None)
    if store is None:
        raise HTTPException(503, "Podaci se još učitavaju.")
    return store  # type: ignore[no-any-return]


def get_planner(request: Request) -> Planner:
    """Dependency: the planner (built with the store)."""
    return request.app.state.planner  # type: ignore[no-any-return]


def make_router(get_session: Callable[..., Any], settings: BlizuSettings) -> APIRouter:
    """Build the router; ``get_session`` is the shared DB session dependency."""
    router = APIRouter(prefix="/api/v1", tags=["blizu"])

    class GeocodeResult(BaseModel):
        label: str
        lat: float
        lon: float
        type: str | None = None

    @router.get("/geocode")
    def geocode(
        q: Annotated[str, Query(min_length=3, max_length=120)],
        session: Session = Depends(get_session),  # noqa: B008
    ) -> dict[str, Any]:
        """Address search (OpenStreetMap Nominatim) bounded to Zagreb; cached for 30 days."""
        try:
            result = core_geocode.search(
                session, q, settings=settings, viewbox=ZAGREB_VIEWBOX, bounded=True
            )
        except Exception as exc:
            raise HTTPException(502, "Usluga za pretragu adresa trenutno nije dostupna.") from exc
        items = [
            GeocodeResult(
                label=r.get("display_name", ""),
                lat=float(r["lat"]),
                lon=float(r["lon"]),
                type=r.get("type"),
            ).model_dump()
            for r in result.results
        ]
        return {
            "results": items,
            "attribution": result.attribution,
            "fetched_at": result.fetched_at.isoformat(),
            "from_cache": result.from_cache,
        }

    @router.get("/access")
    def access(
        lat: Lat,
        lon: Lon,
        persona: Persona,
        store: DataStore = Depends(get_store),  # noqa: B008
    ) -> dict[str, Any]:
        """Walking minutes to the nine service categories and the Blizu index of an address."""
        try:
            return service.compute_access(store, lat, lon, persona)
        except service.OutsideZagrebError as exc:
            raise HTTPException(422, str(exc)) from exc
        except service.FarFromNetworkError as exc:
            raise HTTPException(
                422,
                f"Adresa daleko od pješačke mreže ({round(exc.snapped_m)} m od najbliže staze).",
            ) from exc

    @router.get("/scoring")
    def scoring(store: DataStore = Depends(get_store)) -> dict[str, Any]:  # noqa: B008
        """The versioned scoring configuration (scoring.yaml) used by every calculation."""
        return dict(store.cfg.raw)

    @router.get("/compare")
    def compare(
        a: Annotated[str, Query(max_length=40)],
        b: Annotated[str, Query(max_length=40)],
        persona: Persona,
        store: DataStore = Depends(get_store),  # noqa: B008
    ) -> dict[str, Any]:
        """Two addresses side by side (``a=lat,lon``, ``b=lat,lon``)."""
        pa, pb = parse_latlon(a, "a"), parse_latlon(b, "b")
        try:
            return service.compare(store, pa, pb, persona)
        except service.OutsideZagrebError as exc:
            raise HTTPException(422, str(exc)) from exc
        except service.FarFromNetworkError as exc:
            raise HTTPException(
                422,
                f"Adresa daleko od pješačke mreže ({round(exc.snapped_m)} m od najbliže staze).",
            ) from exc

    @router.get("/facilities")
    def facilities(
        bbox: Annotated[str, Query(max_length=80)],
        category: Category | None = None,
        store: DataStore = Depends(get_store),  # noqa: B008
    ) -> dict[str, Any]:
        """Facilities in a bounding box as GeoJSON (at most 2000 features)."""
        min_lon, min_lat, max_lon, max_lat = parse_bbox(bbox)
        df = store.facilities
        mask = (
            (df["lon"] >= min_lon)
            & (df["lon"] <= max_lon)
            & (df["lat"] >= min_lat)
            & (df["lat"] <= max_lat)
        )
        if category:
            mask &= df["category"] == category
        sub = df[mask]
        total = len(sub)
        features = [
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [float(r.lon), float(r.lat)]},
                "properties": {
                    "id": int(r.id),
                    "category": r.category,
                    "name": service.display_name(store, r.category, r.name),
                    "address": r.address,
                    "source_id": r.source_id,
                    "tier": r.tier,
                },
            }
            for r in sub.head(MAX_FEATURES).itertuples(index=False)
        ]
        return {
            "type": "FeatureCollection",
            "features": features,
            "total": total,
            "truncated": total > MAX_FEATURES,
        }

    @router.get("/plan/need")
    def plan_need(
        category: Category,
        persona: Persona,
        planner: Planner = Depends(get_planner),  # noqa: B008
    ) -> dict[str, Any]:
        """Unmet need per 1 km cell (GeoJSON) and a summary."""
        return planner.need(category, persona)

    @router.post("/plan/optimise")
    def plan_optimise(
        body: OptimiseRequest,
        planner: Planner = Depends(get_planner),  # noqa: B008
    ) -> dict[str, Any]:
        """Best sites for 1-5 new facilities (greedy maximum coverage on the walking network)."""
        return planner.optimise(body.category, body.persona, body.k)

    return router
