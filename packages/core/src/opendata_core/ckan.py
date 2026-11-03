"""Client for the data.gov.hr CKAN 3 action API.

NOTE: the portal's root ``/api/3`` returns HTML; the real API lives under ``/ckan/``.
Calls are throttled to at most 2 requests per second (portal usage policy / courtesy).
"""

from __future__ import annotations

import threading
import time
from collections.abc import Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import httpx

from opendata_core import http as http_mod
from opendata_core.config import CoreSettings

BASE = "https://data.gov.hr/ckan/api/3/action"
MIN_INTERVAL_S = 0.5  # <= 2 requests per second


class CkanError(Exception):
    """The CKAN API reported ``success: false`` or an HTTP-level failure."""

    def __init__(
        self, message: str, *, status_code: int | None = None, payload: Any = None
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.payload = payload


class _Throttle:
    """Thread-safe minimum interval between calls."""

    def __init__(self, min_interval_s: float) -> None:
        self.min_interval_s = min_interval_s
        self._lock = threading.Lock()
        self._last = 0.0

    def wait(self) -> None:
        with self._lock:
            delay = self._last + self.min_interval_s - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            self._last = time.monotonic()


_throttle = _Throttle(MIN_INTERVAL_S)


class CkanClient:
    """Thin wrapper over the CKAN action API. Build once, reuse."""

    def __init__(
        self,
        settings: CoreSettings | None = None,
        *,
        client: httpx.Client | None = None,
        base: str = BASE,
        throttle: _Throttle | None = None,
    ) -> None:
        self.settings = settings or CoreSettings()
        self.client = client or http_mod.make_client(self.settings)
        self.base = base.rstrip("/")
        self._throttle = throttle or _throttle

    def action(self, name: str, params: Mapping[str, Any] | None = None) -> Any:
        """Call a CKAN action and return ``result``; raise :class:`CkanError` on failure."""
        self._throttle.wait()
        url = f"{self.base}/{name}"
        clean = {k: v for k, v in (params or {}).items() if v is not None}
        try:
            payload = http_mod.get_json(self.client, url, clean)
        except httpx.HTTPStatusError as exc:
            body: Any = None
            message = f"HTTP {exc.response.status_code} from {name}"
            try:
                body = exc.response.json()
                detail = body.get("error", {}).get("message") if isinstance(body, dict) else None
                if detail:
                    message = f"{message}: {detail}"
            except ValueError:
                pass
            raise CkanError(message, status_code=exc.response.status_code, payload=body) from exc
        except ValueError as exc:  # JSON decode error (e.g. HTML from the wrong base path)
            raise CkanError(f"{name}: response is not JSON ({exc})") from exc
        if not isinstance(payload, dict) or not payload.get("success"):
            raise CkanError(f"{name}: success is not true", payload=payload)
        return payload["result"]

    def status_show(self) -> dict[str, Any]:
        """Portal status incl. ``ckan_version``."""
        return dict(self.action("status_show"))

    def package_show(self, id_or_name: str) -> dict[str, Any]:
        """Full dataset (package) metadata incl. resources."""
        return dict(self.action("package_show", {"id": id_or_name}))

    def package_search(
        self, q: str, rows: int = 50, start: int = 0, fq: str | None = None
    ) -> dict[str, Any]:
        """Search datasets; returns ``{"count": int, "results": [...] , ...}``."""
        return dict(self.action("package_search", {"q": q, "rows": rows, "start": start, "fq": fq}))

    def resource_show(self, id: str) -> dict[str, Any]:  # noqa: A002
        """Single resource metadata."""
        return dict(self.action("resource_show", {"id": id}))

    def download(self, resource_url: str, dest: Path) -> tuple[Path, str]:
        """Download a resource file to ``dest``; returns ``(path, sha256)``."""
        self._throttle.wait()
        return http_mod.download_file(self.client, resource_url, dest)


def _parse_ts(value: Any) -> datetime:
    """Parse CKAN timestamps (naive ISO, UTC). Missing/invalid values sort first."""
    if isinstance(value, str) and value:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return datetime.min.replace(tzinfo=UTC)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    return datetime.min.replace(tzinfo=UTC)


def newest_resource(pkg: Mapping[str, Any], formats: Iterable[str]) -> dict[str, Any] | None:
    """Pick the newest resource of ``pkg`` whose format is in ``formats`` (case-insensitive).

    Ordered by ``last_modified`` then ``created``. Returns ``None`` if nothing matches.
    """
    wanted = {f.strip().upper() for f in formats}
    candidates = [
        r for r in pkg.get("resources", []) if str(r.get("format", "")).strip().upper() in wanted
    ]
    if not candidates:
        return None
    best = max(
        candidates, key=lambda r: (_parse_ts(r.get("last_modified")), _parse_ts(r.get("created")))
    )
    return dict(best)


# Module-level convenience wrappers around a lazily created default client.
_default: CkanClient | None = None


def _client() -> CkanClient:
    global _default
    if _default is None:
        _default = CkanClient()
    return _default


def status_show() -> dict[str, Any]:
    """See :meth:`CkanClient.status_show`."""
    return _client().status_show()


def package_show(id_or_name: str) -> dict[str, Any]:
    """See :meth:`CkanClient.package_show`."""
    return _client().package_show(id_or_name)


def package_search(q: str, rows: int = 50, start: int = 0, fq: str | None = None) -> dict[str, Any]:
    """See :meth:`CkanClient.package_search`."""
    return _client().package_search(q, rows=rows, start=start, fq=fq)


def resource_show(id: str) -> dict[str, Any]:  # noqa: A002
    """See :meth:`CkanClient.resource_show`."""
    return _client().resource_show(id)


def download(resource_url: str, dest: Path) -> tuple[Path, str]:
    """See :meth:`CkanClient.download`."""
    return _client().download(resource_url, dest)
