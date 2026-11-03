"""Blizu settings (extends the shared CoreSettings)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field

from opendata_core.config import CoreSettings


class BlizuSettings(CoreSettings):
    """Environment: DATABASE_URL, CONTACT_EMAIL, NOMINATIM_URL, HF_HOME, CORS_ORIGINS, DATA_DIR."""

    app_name: str = "blizu"
    data_dir: Path = Path("apps/blizu/data")
    hf_home: str | None = None
    semantic_search: bool = True  # /search uses the e5 model when the extra is installed
    osm_feature_source: Literal["auto", "overpass", "geofabrik"] = "auto"
    cors_origins: str = Field(
        default="http://localhost:5173,http://127.0.0.1:5173",
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
    def derived_dir(self) -> Path:
        """Derived artefacts: graph, access arrays, GeoPackage (not committed)."""
        return self.data_dir / "derived"

    @property
    def evidence_dir(self) -> Path:
        """Raw probe responses (committed)."""
        return self.data_dir / "evidence"


@lru_cache
def get_settings() -> BlizuSettings:
    """Process-wide settings."""
    return BlizuSettings()
