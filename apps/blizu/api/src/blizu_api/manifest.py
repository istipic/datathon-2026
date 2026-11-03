"""Manifest of derived artefacts (``data/derived/manifest.json``).

Each ingestion step records the file it produced (name, sha256, date). The API reads the manifest
at start-up to find the *current* graph/access files, so file names with dates can pile up safely.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any


def sha256_file(path: Path) -> str:
    """sha256 of a file (streamed)."""
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class Manifest:
    """Small JSON key/value store next to the derived files."""

    def __init__(self, derived_dir: Path) -> None:
        self.dir = derived_dir
        self.path = derived_dir / "manifest.json"

    def read(self) -> dict[str, Any]:
        """Whole manifest (empty if missing)."""
        if not self.path.exists():
            return {}
        return json.loads(self.path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]

    def get(self, key: str) -> dict[str, Any] | None:
        """Entry for ``key`` or None."""
        value = self.read().get(key)
        return value if isinstance(value, dict) else None

    def set(self, key: str, **info: Any) -> None:
        """Merge ``info`` into entry ``key`` and stamp ``updated_at`` (UTC)."""
        data = self.read()
        entry = dict(data.get(key, {}))
        entry.update(info)
        entry["updated_at"] = datetime.now(UTC).isoformat()
        data[key] = entry
        self.dir.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")

    def path_of(self, key: str, field: str = "file") -> Path:
        """Absolute path of the file recorded under ``key`` (raises KeyError if absent)."""
        entry = self.get(key)
        if not entry or field not in entry:
            raise KeyError(f"manifest has no '{key}.{field}'; run `blizu ingest` first")
        return self.dir / str(entry[field])
