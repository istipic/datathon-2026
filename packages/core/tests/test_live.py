"""Live smoke tests (real network). Run with: RUN_LIVE=1 uv run pytest -m live packages/core"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from pathlib import Path

import pytest

from opendata_core import ckan
from opendata_core import http as http_mod
from opendata_core.config import CoreSettings

pytestmark = pytest.mark.live


@pytest.fixture
def live_settings() -> CoreSettings:
    email = os.environ.get("CONTACT_EMAIL", "")
    if not email:
        pytest.skip("CONTACT_EMAIL must be set for live tests (identifying User-Agent)")
    return CoreSettings(_env_file=None, app_name="datathon-core-tests", contact_email=email)  # type: ignore[call-arg]


def test_ckan_status_show_live(live_settings: CoreSettings, fixtures_dir: Path) -> None:
    client = ckan.CkanClient(live_settings)
    # Record the raw response as a dated fixture (once per day).
    raw = http_mod.fetch(client.client, "GET", f"{ckan.BASE}/status_show")
    fixture = fixtures_dir / "ckan" / f"{datetime.now(UTC):%Y-%m-%d}_status_show_live.json"
    if not fixture.exists():
        fixture.write_bytes(raw.content)

    result = client.status_show()
    assert raw.json()["success"] is True
    assert result["ckan_version"]
    assert result["site_url"].startswith("https://data.gov.hr")
