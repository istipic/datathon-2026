"""Croatian number formatting for server-rendered text."""

from __future__ import annotations


def fmt_int(value: int | float | None) -> str:
    """Integer with a dot as thousands separator (49669 -> ``49.669``); ``–`` for ``None``."""
    if value is None:
        return "–"
    return f"{round(value):,}".replace(",", ".")
