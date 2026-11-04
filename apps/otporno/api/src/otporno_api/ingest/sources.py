"""Registration of Otporko's data sources (``data_source`` rows)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from opendata_core.popgrid import register_popgrid_source
from opendata_core.provenance import AccessMethod, Tier, register_source
from otporno_api.constants import (
    SRC_CORINE,
    SRC_DERIVED,
    SRC_DHMZ,
    SRC_HV_FLOOD,
    SRC_LAU,
    SRC_OPEN_METEO,
    SRC_OSM_BUILDINGS,
)
from otporno_api.settings import OtpornoSettings


def register_all(session: Session, settings: OtpornoSettings) -> None:
    """Idempotently register every source used by the app."""
    register_source(
        session,
        id=SRC_HV_FLOOD,
        title="Karte opasnosti od poplava 2019. (WMS)",
        publisher="Hrvatske vode",
        url="https://www.voda.hr/hr/karte-opasnosti-od-poplava-i-karte-rizika-od-poplava-2019",
        access_method=AccessMethod.wms,
        tier=Tier.official,
        notes=(
            "Three scenarios (velika ~25, srednja ~100, mala ~1000 godina povratnog razdoblja, as stated by "
            "Hrvatske vode). WMS GetMap works (overlay); the hazard layers are not queryable (GetFeatureInfo "
            "LayerNotQueryable), WFS is disabled and no vector download exists: flood level is not computed "
            "automatically (ladder step c, docs/adr/0007). Informational maps, no guarantee."
        ),
    )
    register_source(
        session,
        id=SRC_OPEN_METEO,
        title="Open-Meteo Climate API (CMIP6 models CMCC_CM2_VHR4, EC_Earth3P_HR, MRI_AGCM3_2_S)",
        publisher="Open-Meteo.com",
        url="https://open-meteo.com/en/docs/climate-api",
        license_name="CC BY 4.0",
        license_url="https://open-meteo.com/en/licence",
        access_method=AccessMethod.api,
        tier=Tier.community,
        notes=(
            "Daily temperature_2m_max/min; hot day Tmax >= 30 C, tropical night Tmin >= 20 C; base 1991-2020, "
            "future 2031-2050. Free tier is cost-limited (600/min, 5000/h, 10000/day; a 3-model request costs "
            "~470-780): the national grid is fetched gradually. Attribution: Open-Meteo.com, CC BY 4.0."
        ),
    )
    register_popgrid_source(session)
    register_source(
        session,
        id=SRC_LAU,
        title="GISCO LAU 2024 (lokalne administrativne jedinice)",
        publisher="Eurostat (GISCO)",
        url="https://ec.europa.eu/eurostat/web/gisco/geodata/statistical-units/local-administrative-units",
        license_name="© EuroGeographics for the administrative boundaries",
        license_url="https://ec.europa.eu/eurostat/web/gisco/geodata/administrative-units",
        access_method=AccessMethod.download,
        tier=Tier.eu_official,
        notes="LAU_RG_01M_2024_4326.geojson, Croatia only (CNTR_CODE = HR).",
    )
    register_source(
        session,
        id=SRC_OSM_BUILDINGS,
        title="OpenStreetMap: javne zgrade kao kandidati za centre za rashlađivanje",
        publisher="OpenStreetMap contributors",
        url="https://www.openstreetmap.org/",
        license_name="ODbL 1.0",
        license_url="https://www.openstreetmap.org/copyright",
        access_method=AccessMethod.api,
        tier=Tier.community,
        notes="amenity in (library, school, community_centre, social_facility, townhall); Overpass, else Geofabrik extract.",
    )
    register_source(
        session,
        id=SRC_DHMZ,
        title="DHMZ: trenutni podaci s meteoroloških postaja (XML)",
        publisher="Državni hidrometeorološki zavod",
        url=settings.dhmz_url,
        access_method=AccessMethod.api,
        tier=Tier.official,
        notes="P1. Cached 30 minutes; hidden when the observation is older than 3 hours.",
    )
    register_source(
        session,
        id=SRC_CORINE,
        title="CORINE Land Cover 2018 (šume i grmlje, klase 311-324)",
        publisher="Copernicus Land Monitoring Service / EEA",
        url="https://land.copernicus.eu/en/products/corine-land-cover/clc2018",
        access_method=AccessMethod.download,
        tier=Tier.eu_official,
        notes="P1: wildfire exposure.",
    )
    register_source(
        session,
        id=SRC_DERIVED,
        title="Otporko: izvedeni podaci (toplinski pokazatelji po ćeliji, prioriteti, centri za rashlađivanje)",
        publisher="Otporko",
        url="https://github.com/",
        access_method=AccessMethod.derived,
        tier=Tier.derived,
        notes="Computed from the sources above.",
    )
    session.commit()
