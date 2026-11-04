"""Weekly e-mail digest: double opt-in subscriptions and the digest itself.

Only the e-mail address is stored (plus the OIB / free-text query that defines the digest). Tokens:

- confirmation: ``<id>.<random>``; only sha256(token) is stored (``token_hash``);
- unsubscribe: ``<id>.<HMAC-SHA256(secret, "unsub:<id>")>`` - verifiable without storing it, so the
  digest e-mail can carry an unsubscribe link while the database holds no usable token.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from nabavaradar_api.db import Subscription
from nabavaradar_api.match import CompanyNotLoaded, MatchEngine, build_profile
from nabavaradar_api.oib import is_valid_oib
from nabavaradar_api.settings import NabavaSettings
from opendata_core.email import make_template_env, render_email, send_email

log = structlog.get_logger(__name__)

CONSENT_TEXT = (
    "Pristajem da NabavaRadar na ovu e-adresu jednom tjedno (ponedjeljkom u 7:00) šalje pregled do 10 novih "
    "natječaja koji odgovaraju mojoj pretrazi. Pohranjuje se samo e-adresa. Pretplatu mogu otkazati "
    "poveznicom u svakoj poruci."
)
# RFC 5322 "basic": local part of atext characters and dots, domain labels; MX is not checked
EMAIL_RE = re.compile(
    r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*@([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}$"
)
MAX_EMAIL = 254
DIGEST_SIZE = 10
FIRST_DIGEST_DAYS = 7
TEMPLATES = Path(__file__).parent / "templates"
DEV_SECRET = "dev-only-subscription-secret"  # noqa: S105 - never used when env == "prod"


def _secret(settings: NabavaSettings) -> bytes:
    value = settings.subscription_secret.get_secret_value()
    if not value:
        if settings.is_prod:
            raise RuntimeError("SUBSCRIPTION_SECRET must be set in production")
        value = DEV_SECRET
    return value.encode()


def hash_token(token: str) -> str:
    """sha256 of a confirmation token (what the database stores)."""
    return hashlib.sha256(token.encode()).hexdigest()


def make_confirm_token(sub_id: int) -> str:
    """Fresh confirmation token for subscription ``sub_id``."""
    return f"{sub_id}.{secrets.token_urlsafe(24)}"


def make_unsub_token(sub_id: int, settings: NabavaSettings) -> str:
    """Unsubscribe token (HMAC of the id)."""
    mac = hmac.new(_secret(settings), f"unsub:{sub_id}".encode(), hashlib.sha256).hexdigest()
    return f"{sub_id}.{mac}"


def parse_unsub_token(token: str, settings: NabavaSettings) -> int | None:
    """Subscription id of a valid unsubscribe token, else ``None`` (constant-time comparison)."""
    head, _, _ = token.partition(".")
    if not head.isdigit():
        return None
    return int(head) if hmac.compare_digest(make_unsub_token(int(head), settings), token) else None


class SubscribeRequest(BaseModel):
    """Body of ``POST /subscriptions``."""

    email: str = Field(max_length=MAX_EMAIL)
    oib: str | None = None
    query: str | None = Field(default=None, max_length=500)
    consent: bool = False


def _links(
    settings: NabavaSettings, confirm: str | None = None, unsub: str | None = None
) -> dict[str, str]:
    base = settings.public_base_url.rstrip("/")
    out: dict[str, str] = {}
    if confirm:
        out["confirm"] = f"{base}/pretplata/potvrda?token={confirm}"
    if unsub:
        out["unsub"] = f"{base}/pretplata/odjava?token={unsub}"
    return out


def send_confirmation(settings: NabavaSettings, email: str, confirm_token: str) -> None:
    """Double opt-in message with the confirmation link."""
    env = make_template_env(TEMPLATES)
    ctx = {"links": _links(settings, confirm=confirm_token), "consent": CONSENT_TEXT}
    send_email(
        email,
        "NabavaRadar: potvrdite pretplatu",
        render_email(env, "confirm.html.j2", **ctx),
        render_email(env, "confirm.txt.j2", **ctx),
        settings=settings,
    )


def make_router(get_session: Any, settings: NabavaSettings) -> APIRouter:
    """``/api/v1/subscriptions`` endpoints."""
    router = APIRouter(prefix="/api/v1/subscriptions")

    @router.post("", status_code=202)
    def subscribe(
        body: SubscribeRequest, session: Session = Depends(get_session)
    ) -> dict[str, str]:
        email = body.email.strip().lower()
        if not EMAIL_RE.match(email):
            raise HTTPException(422, "Neispravna e-adresa.")
        if not body.consent:
            raise HTTPException(422, "Potrebna je privola za slanje tjednog pregleda.")
        oib = body.oib.strip() if body.oib else None
        query = body.query.strip() if body.query and body.query.strip() else None
        if oib is not None and not is_valid_oib(oib):
            raise HTTPException(422, "Neispravan OIB.")
        if oib is None and query is None:
            raise HTTPException(422, "Navedite OIB tvrtke ili opis pretrage.")
        generic = {
            "detail": "Ako je adresa ispravna, poslali smo poruku za potvrdu pretplate. Pretplata je aktivna tek nakon potvrde."
        }
        existing = session.scalars(
            select(Subscription).where(
                Subscription.email == email,
                Subscription.oib.is_(oib) if oib is None else Subscription.oib == oib,
                Subscription.query.is_(query) if query is None else Subscription.query == query,
            )
        ).first()
        if existing is not None and existing.confirmed:
            return generic  # do not reveal that the address is already subscribed
        sub = existing or Subscription(
            email=email,
            oib=oib,
            query=query,
            confirmed=False,
            token_hash="pending",  # noqa: S106 - placeholder, replaced right below
            consent_text=CONSENT_TEXT,
        )
        if existing is None:
            session.add(sub)
            session.flush()
        token = make_confirm_token(sub.id)
        sub.token_hash = hash_token(token)
        session.commit()
        try:
            send_confirmation(settings, email, token)
        except OSError as exc:
            log.error("confirmation_mail_failed", error=type(exc).__name__)
            raise HTTPException(
                503, "Slanje poruke trenutno nije moguće. Pokušajte kasnije."
            ) from exc
        return generic

    @router.get("/confirm")
    def confirm(token: str, session: Session = Depends(get_session)) -> dict[str, str]:
        sub = session.scalars(
            select(Subscription).where(Subscription.token_hash == hash_token(token))
        ).first()
        if sub is None:
            raise HTTPException(404, "Poveznica za potvrdu nije valjana ili je istekla.")
        sub.confirmed = True
        session.commit()
        return {"detail": "Pretplata je potvrđena. Prvi pregled stiže sljedeći ponedjeljak u 7:00."}

    @router.delete("")
    def unsubscribe(token: str, session: Session = Depends(get_session)) -> dict[str, str]:
        sub_id = parse_unsub_token(token, settings)
        if sub_id is None:
            raise HTTPException(404, "Poveznica za odjavu nije valjana.")
        session.execute(delete(Subscription).where(Subscription.id == sub_id))
        session.commit()
        return {"detail": "Pretplata je otkazana i e-adresa je obrisana."}

    return router


def digest_for(
    session: Session, engine: MatchEngine, sub: Subscription, encode: Any, *, now: datetime
) -> list[dict[str, Any]]:
    """Top new matches for a subscription: published since the last digest (or the last 7 days)."""
    since = (sub.last_sent_at or now - timedelta(days=FIRST_DIGEST_DAYS)).date()
    try:
        activities, nuts3, ranked = build_profile(session, oib=sub.oib, q=sub.query, encode=encode)
    except CompanyNotLoaded:
        return []
    if not activities:
        return []
    items = engine.match(
        session,
        activities=activities,
        company_nuts3=nuts3,
        ranked_divisions=ranked,
        limit=200,
        now=now,
    )
    fresh = [i for i in items if i["pub_date"] >= since.isoformat()]
    return fresh[:DIGEST_SIZE]


def send_digests(
    session: Session,
    settings: NabavaSettings,
    engine: MatchEngine,
    encode: Any,
    *,
    dry_run: bool = False,
) -> dict[str, int]:
    """Send the weekly digest to every confirmed subscription that has new matches."""
    now = datetime.now(UTC)
    env = make_template_env(TEMPLATES)
    sent = skipped = 0
    for sub in session.scalars(select(Subscription).where(Subscription.confirmed.is_(True))):
        items = digest_for(session, engine, sub, encode, now=now)
        if not items:
            skipped += 1
            continue
        ctx = {
            "items": items,
            "base": settings.public_base_url.rstrip("/"),
            "links": _links(settings, unsub=make_unsub_token(sub.id, settings)),
        }
        if not dry_run:
            send_email(
                sub.email,
                f"NabavaRadar: {len(items)} novih natječaja ovaj tjedan",
                render_email(env, "digest.html.j2", **ctx),
                render_email(env, "digest.txt.j2", **ctx),
                settings=settings,
            )
            sub.last_sent_at = now
            session.commit()
        sent += 1
    return {"sent": sent, "skipped_no_new_matches": skipped, "dry_run": int(dry_run)}
