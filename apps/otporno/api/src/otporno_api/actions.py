"""Cited action rules: YAML -> ``action_rule`` rows -> the "Što učiniti" lists.

Each rule is a short Croatian recommendation for one hazard and audience that cites a public page
(``source`` -> entry of the ``sources`` list, plus the ``quote`` it rests on). A rule applies from
``min_band`` upwards (``niska`` = always). At most ``MAX_PER_GROUP`` rules are shown, by ``priority``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml  # type: ignore[import-untyped]
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from otporno_api.constants import BANDS
from otporno_api.db import ActionRule

RULES_FILE = Path(__file__).parent / "config" / "action_rules.yaml"
HAZARD_KEYS = ("flood", "heat", "fire")
AUDIENCES = ("gradanin", "opcina")
MAX_PER_GROUP = 6
MAX_TEXT = 260


class RuleError(ValueError):
    """The rules file is malformed."""


def load_document(path: Path = RULES_FILE) -> dict[str, Any]:
    """Parse and validate the YAML; returns ``{"sources": {id: source}, "actions": [...]}``."""
    if not path.exists():
        raise RuleError(f"{path} does not exist")
    doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    sources = {s["id"]: s for s in doc.get("sources") or []}
    actions = doc.get("actions") or []
    if not sources or not actions:
        raise RuleError("the rules file needs 'sources' and 'actions'")
    for s in sources.values():
        if (
            not str(s.get("url", "")).startswith("https://")
            or not s.get("title")
            or not s.get("retrieved")
        ):
            raise RuleError(f"source {s.get('id')}: needs title, https url and retrieved date")
    seen: set[str] = set()
    for a in actions:
        for key in (
            "id",
            "hazard",
            "audience",
            "min_band",
            "priority",
            "text_hr",
            "source",
            "quote",
        ):
            if a.get(key) in (None, ""):
                raise RuleError(f"action {a.get('id', '?')}: missing '{key}'")
        if a["id"] in seen:
            raise RuleError(f"duplicate action id {a['id']}")
        seen.add(a["id"])
        if a["hazard"] not in HAZARD_KEYS:
            raise RuleError(f"{a['id']}: unknown hazard {a['hazard']!r}")
        if a["audience"] not in AUDIENCES:
            raise RuleError(f"{a['id']}: unknown audience {a['audience']!r}")
        if a["min_band"] not in BANDS:
            raise RuleError(f"{a['id']}: unknown min_band {a['min_band']!r}")
        if a["source"] not in sources:
            raise RuleError(f"{a['id']}: unknown source {a['source']!r}")
        if len(str(a["text_hr"])) > MAX_TEXT:
            raise RuleError(f"{a['id']}: text too long")
    return {"sources": sources, "actions": actions}


def sync_rules(session: Session, path: Path = RULES_FILE) -> int:
    """Replace the ``action_rule`` table with the rules of the file; returns the number of rows."""
    doc = load_document(path)
    session.execute(delete(ActionRule))
    for a in doc["actions"]:
        src = doc["sources"][a["source"]]
        session.add(
            ActionRule(
                id=a["id"],
                hazard=a["hazard"],
                band=a["min_band"],
                audience=a["audience"],
                text_hr=str(a["text_hr"]).strip(),
                source_title=str(src["title"]).strip(),
                source_url=str(src["url"]).strip(),
            )
        )
    session.commit()
    return len(doc["actions"])


def _priorities(path: Path = RULES_FILE) -> dict[str, int]:
    return {a["id"]: int(a["priority"]) for a in load_document(path)["actions"]}


def actions_for(
    session: Session, hazard: str, band: str | None, audience: str = "gradanin"
) -> list[dict[str, str]]:
    """Rules of a hazard that apply at ``band`` (``None`` = unknown: only the always-applicable ones).

    Ordered by priority, at most six.
    """
    level = 0 if band is None else BANDS.index(band)
    rows = session.scalars(
        select(ActionRule).where(ActionRule.hazard == hazard, ActionRule.audience == audience)
    ).all()
    prio = _priorities()
    fit = [r for r in rows if BANDS.index(r.band) <= level]
    fit.sort(key=lambda r: (prio.get(r.id, 10_000), r.id))
    return [
        {"id": r.id, "text": r.text_hr, "source_title": r.source_title, "source_url": r.source_url}
        for r in fit[:MAX_PER_GROUP]
    ]
