"""Otporko settings (extends the shared CoreSettings)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field

from opendata_core.config import CoreSettings


class OtpornoSettings(CoreSettings):
    """Environment: DATABASE_URL, CONTACT_EMAIL, NOMINATIM_URL, CORS_ORIGINS, OPEN_METEO_CLIMATE_URL,
    HV_WMS_URL, DATA_DIR."""

    app_name: str = "otporno"
    data_dir: Path = Path("apps/otporno/data")
    open_meteo_climate_url: str = "https://climate-api.open-meteo.com/v1/climate"
    hv_wms_url: str = "https://servisi.voda.hr/wms"
    overpass_url: str = "https://overpass-api.de/api/interpreter"
    gisco_lau_url: str = "https://gisco-services.ec.europa.eu/distribution/v2/lau/geojson/LAU_RG_01M_2024_4326.geojson"
    dhmz_url: str = "https://vrijeme.hr/hrvatska_n.xml"
    corine_url: str = (
        "https://image.discomap.eea.europa.eu/arcgis/rest/services/Corine/CLC2018_WM/MapServer"
    )
    cors_origins: str = Field(
        default="http://localhost:5175,http://127.0.0.1:5175",
        description="Comma-separated list of allowed browser origins.",
    )

    @property
    def cors_origin_list(self) -> list[str]:
        """CORS origins as a list (explicit origins only)."""
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def raw_dir(self) -> Path:
        """Downloaded source files (not committed)."""
        return self.data_dir / "raw"

    @property
    def evidence_dir(self) -> Path:
        """Raw probe responses (committed)."""
        return self.data_dir / "evidence"


@lru_cache
def get_settings() -> OtpornoSettings:
    """Process-wide settings."""
    return OtpornoSettings()
