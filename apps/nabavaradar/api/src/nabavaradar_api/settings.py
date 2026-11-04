"""NabavaRadar settings (extends the shared CoreSettings)."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr

from opendata_core.config import CoreSettings

PROD_SUDREG_BASE = "https://sudreg-data.gov.hr/api/javni"
PROD_SUDREG_TOKEN = "https://sudreg-data.gov.hr/api/oauth/token"  # noqa: S105 - a URL, not a secret


class NabavaSettings(CoreSettings):
    """Environment: DATABASE_URL, CONTACT_EMAIL, SUDREG_*, TED_SEARCH_URL, SMTP_*, PUBLIC_BASE_URL,
    HF_HOME, CORS_ORIGINS, DATA_DIR."""

    app_name: str = "nabavaradar"
    data_dir: Path = Path("apps/nabavaradar/data")
    hf_home: str | None = None

    sudreg_client_id: str = ""
    sudreg_client_secret: SecretStr = SecretStr("")
    sudreg_base_url: str = PROD_SUDREG_BASE
    sudreg_token_url: str = PROD_SUDREG_TOKEN

    # signs unsubscribe tokens (HMAC); required in prod, a fixed dev value is used when env == "dev"
    subscription_secret: SecretStr = SecretStr("")

    ted_search_url: str = "https://api.ted.europa.eu/v3/notices/search"
    competition_days: int = 120  # window of competition notices (spec: last 120 days)
    result_months: int = 36  # window of result notices (spec: last 36 months)

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
    def evidence_dir(self) -> Path:
        """Raw probe responses (committed)."""
        return self.data_dir / "evidence"

    @property
    def sudreg_is_test(self) -> bool:
        """True when the configured Sudreg host is the test environment."""
        return "sudreg-data-test" in self.sudreg_base_url


@lru_cache
def get_settings() -> NabavaSettings:
    """Process-wide settings."""
    return NabavaSettings()
