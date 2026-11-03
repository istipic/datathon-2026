"""Shared settings loaded from environment variables / ``.env``."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class CoreSettings(BaseSettings):
    """Settings shared by every app. Apps may subclass to add their own fields.

    Values come from the process environment (case-insensitive) and from ``.env``.
    No secrets have defaults: an unset secret stays empty/None.
    """

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "datathon"
    env: Literal["dev", "prod"] = "dev"
    database_url: str | None = None
    log_level: str = "INFO"
    contact_email: str = ""
    http_cache_dir: Path = Path(".http-cache")
    http_timeout_s: float = 20
    nominatim_url: str = "https://nominatim.openstreetmap.org"
    smtp_host: str = "127.0.0.1"
    smtp_port: int = 1025
    smtp_user: str = ""
    smtp_password: str = ""
    smtp_from: str = "no-reply@localhost"
    public_base_url: str = "http://localhost:5173"
    git_sha: str = "dev"

    @property
    def is_prod(self) -> bool:
        """True when running with ``env == "prod"``."""
        return self.env == "prod"
