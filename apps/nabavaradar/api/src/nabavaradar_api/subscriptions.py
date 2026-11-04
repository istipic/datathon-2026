"""E-mail alerts: double opt-in subscriptions, threshold alerts and the weekly summary.

Only the e-mail address is stored, plus the OIB / free-text query that defines the profile and the alert
settings (threshold, filters, frequency). Tokens:

- confirmation: ``<id>.<random>``; only sha256(token) is stored (``token_hash``);
- unsubscribe / settings: ``<id>.<HMAC-SHA256(secret, "<purpose>:<id>")>`` - verifiable without storing
  them, so every e-mail can carry both links while the database holds no usable token.

A notice is e-mailed to a subscriber at most once (table ``alert_sent``). It qualifies when its fit for
the subscriber's profile is at least ``min_fit``, it passes the filters, its deadline is still ahead and
the subscriber has not excluded it ("Ne zanima me").
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated, Any, Literal

import structlog
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from nabavaradar_api.counties import counties
from nabavaradar_api.db import AlertExclusion, AlertSent, Notice, Subscription
from nabavaradar_api.fit import FitConfig, load_fit_config
from nabavaradar_api.match import CompanyNotLoaded, MatchEngine, build_profile_full
from nabavaradar_api.oib import is_valid_oib
from nabavaradar_api.settings import NabavaSettings
from opendata_core.email import make_template_env, render_email, send_email

log = structlog.get_logger(__name__)

# RFC 5322 "basic": local part of atext characters and dots, domain labels; MX is not checked
EMAIL_RE = re.compile(
    r"^[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+(\.[A-Za-z0-9!#$%&'*+/=?^_`{|}~-]+)*@([A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)+[A-Za-z]{2,}$"
)
MAX_EMAIL = 254
ALERT_CAP = 20  # most notices in one e-mail
MIN_FIT_RANGE = (0.5, 0.95)
DEFAULT_MIN_FIT = 0.75
TEMPLATES = Path(__file__).parent / "templates"
DEV_SECRET = "dev-only-subscription-secret"  # noqa: S105 - never used when env == "prod"
SUBSCRIBE_PER_IP_HOUR = 10
SUBSCRIBE_PER_EMAIL_HOUR = 3

Frequency = Literal["daily", "weekly"]


def consent_text(frequency: str, min_fit: float) -> str:
    """The exact consent sentence shown next to the checkbox and stored with the subscription."""
    pct = round(min_fit * 100)
    when = (
        "najviše jednom dnevno (u 7:00) šalje obavijest o natječajima"
        if frequency == "daily"
        else "jednom tjedno (ponedjeljkom u 7:00) šalje pregled natječaja"
    )
    return (
        f"Pristajem da Birokratko na ovu e-adresu {when} čija prilagodba mojem profilu iznosi "
        f"najmanje {pct} %. Pohranjuju se samo e-adresa, OIB ili opis pretrage i postavke "
        "upozorenja. Pretplatu mogu promijeniti ili otkazati poveznicom u svakoj poruci."
    )


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


def _hmac_token(sub_id: int, purpose: str, settings: NabavaSettings) -> str:
    mac = hmac.new(_secret(settings), f"{purpose}:{sub_id}".encode(), hashlib.sha256).hexdigest()
    return f"{sub_id}.{mac}"


def _parse_hmac_token(token: str, purpose: str, settings: NabavaSettings) -> int | None:
    head, _, _ = token.partition(".")
    if not head.isdigit():
        return None
    ok = hmac.compare_digest(_hmac_token(int(head), purpose, settings), token)
    return int(head) if ok else None


def make_unsub_token(sub_id: int, settings: NabavaSettings) -> str:
    """Unsubscribe token (HMAC of the id)."""
    return _hmac_token(sub_id, "unsub", settings)


def parse_unsub_token(token: str, settings: NabavaSettings) -> int | None:
    """Subscription id of a valid unsubscribe token, else ``None`` (constant-time comparison)."""
    return _parse_hmac_token(token, "unsub", settings)


def make_settings_token(sub_id: int, settings: NabavaSettings) -> str:
    """Token of the "Promijeni postavke" link (HMAC of the id, different purpose than unsubscribe)."""
    return _hmac_token(sub_id, "settings", settings)


def parse_settings_token(token: str, settings: NabavaSettings) -> int | None:
    """Subscription id of a valid settings token, else ``None``."""
    return _parse_hmac_token(token, "settings", settings)


def _valid_county_codes() -> set[int]:
    return {c.code for c in counties()}


class AlertPrefs(BaseModel):
    """Alert settings shared by sign-up and the settings page."""

    min_fit: float = Field(default=DEFAULT_MIN_FIT, ge=MIN_FIT_RANGE[0], le=MIN_FIT_RANGE[1])
    min_value_eur: float | None = Field(default=None, ge=0, le=10_000_000_000)
    counties: list[int] = Field(default_factory=list, max_length=21)
    cpv_divisions: list[Annotated[str, Field(pattern=r"^\d{2}$")]] = Field(
        default_factory=list, max_length=50
    )
    frequency: Frequency = "daily"


class SubscribeRequest(AlertPrefs):
    """Body of ``POST /subscriptions``."""

    email: str = Field(max_length=MAX_EMAIL)
    oib: str | None = None
    query: str | None = Field(default=None, max_length=500)
    consent: bool = False


class SettingsUpdate(BaseModel):
    """Body of ``PUT /subscriptions/settings`` (every field optional)."""

    min_fit: float | None = Field(default=None, ge=MIN_FIT_RANGE[0], le=MIN_FIT_RANGE[1])
    min_value_eur: float | None = Field(default=None, ge=0, le=10_000_000_000)
    clear_min_value: bool = False
    counties: list[int] | None = Field(default=None, max_length=21)
    cpv_divisions: list[Annotated[str, Field(pattern=r"^\d{2}$")]] | None = Field(
        default=None, max_length=50
    )
    frequency: Frequency | None = None
    paused: bool | None = None


class ExcludeRequest(BaseModel):
    """Body of ``POST /subscriptions/exclude``: "Ne zanima me" for one notice."""

    pub_no: str = Field(pattern=r"^\d{1,7}-\d{4}$")


def _check_counties(codes: list[int]) -> list[int]:
    unknown = set(codes) - _valid_county_codes()
    if unknown:
        raise HTTPException(422, "Nepoznata županija.")
    return sorted(set(codes))


def _links(
    settings: NabavaSettings,
    confirm: str | None = None,
    unsub: str | None = None,
    prefs: str | None = None,
) -> dict[str, str]:
    base = settings.public_base_url.rstrip("/")
    out: dict[str, str] = {}
    if confirm:
        out["confirm"] = f"{base}/pretplata/potvrda?token={confirm}"
    if unsub:
        out["unsub"] = f"{base}/pretplata/odjava?token={unsub}"
    if prefs:
        out["settings"] = f"{base}/pretplata/postavke?token={prefs}"
    return out


def send_confirmation(
    settings: NabavaSettings, email: str, confirm_token: str, consent: str | None = None
) -> None:
    """Double opt-in message with the confirmation link."""
    env = make_template_env(TEMPLATES)
    ctx = {
        "links": _links(settings, confirm=confirm_token),
        "consent": consent or consent_text("daily", DEFAULT_MIN_FIT),
    }
    send_email(
        email,
        "Birokratko: potvrdite pretplatu",
        render_email(env, "confirm.html.j2", **ctx),
        render_email(env, "confirm.txt.j2", **ctx),
        settings=settings,
    )


def _mask(email: str) -> str:
    local, _, domain = email.partition("@")
    return f"{local[:1]}{'*' * max(len(local) - 1, 1)}@{domain}"


def _prefs_payload(sub: Subscription, excluded: int) -> dict[str, Any]:
    return {
        "email": _mask(sub.email),
        "oib": sub.oib,
        "query": sub.query,
        "min_fit": sub.min_fit,
        "min_value_eur": float(sub.min_value_eur) if sub.min_value_eur is not None else None,
        "counties": list(sub.counties or []),
        "cpv_divisions": list(sub.cpv_divisions or []),
        "frequency": sub.frequency,
        "paused": sub.paused,
        "confirmed": sub.confirmed,
        "excluded": excluded,
    }


def make_router(
    get_session: Any,
    settings: NabavaSettings,
    engine: MatchEngine | None = None,
    encode: Any = None,
) -> APIRouter:
    """``/api/v1/subscriptions`` endpoints."""
    from nabavaradar_api.api import SlidingLimit

    router = APIRouter(prefix="/api/v1/subscriptions")
    engine = engine or MatchEngine()
    ip_limit = SlidingLimit(SUBSCRIBE_PER_IP_HOUR, 3600.0)
    email_limit = SlidingLimit(SUBSCRIBE_PER_EMAIL_HOUR, 3600.0)

    def _encode(texts: list[str]) -> Any:
        if encode is not None:
            return encode(texts)
        from opendata_core import semantic

        return semantic.encode_queries(texts)

    def _sub_for(token: str, session: Session) -> Subscription:
        sub_id = parse_settings_token(token, settings)
        sub = session.get(Subscription, sub_id) if sub_id is not None else None
        if sub is None:
            raise HTTPException(404, "Poveznica za postavke nije valjana.")
        return sub

    @router.get("/consent")
    def consent(
        frequency: Frequency = "daily",
        min_fit: Annotated[
            float, Query(ge=MIN_FIT_RANGE[0], le=MIN_FIT_RANGE[1])
        ] = DEFAULT_MIN_FIT,
    ) -> dict[str, str]:
        """The consent sentence for the chosen settings (the same text is stored on sign-up)."""
        return {"text": consent_text(frequency, min_fit)}

    @router.get("/preview")
    def preview(
        oib: Annotated[str | None, Query(min_length=11, max_length=11)] = None,
        q: Annotated[str | None, Query(max_length=500)] = None,
        min_fit: Annotated[
            float, Query(ge=MIN_FIT_RANGE[0], le=MIN_FIT_RANGE[1])
        ] = DEFAULT_MIN_FIT,
        min_value_eur: Annotated[float | None, Query(ge=0)] = None,
        counties_csv: Annotated[str | None, Query(alias="counties", max_length=120)] = None,
        cpv: Annotated[str | None, Query(max_length=300)] = None,
        session: Session = Depends(get_session),
    ) -> dict[str, Any]:
        """How many open notices qualify right now with these settings."""
        if oib is None and not (q and q.strip()):
            raise HTTPException(422, "Navedite OIB tvrtke ili opis djelatnosti.")
        if oib is not None and not is_valid_oib(oib):
            raise HTTPException(422, "Neispravan OIB.")
        codes = [int(c) for c in (counties_csv or "").split(",") if c.strip().isdigit()]
        divisions = [d for d in (cpv or "").split(",") if re.fullmatch(r"\d{2}", d.strip())]
        try:
            profile = build_profile_full(session, oib=oib, q=q, encode=_encode)
        except CompanyNotLoaded as exc:
            raise HTTPException(404, "Tvrtka nije učitana.") from exc
        items = qualifying(
            session,
            engine,
            profile=profile,
            min_fit=min_fit,
            min_value_eur=min_value_eur,
            counties_codes=_check_counties(codes),
            cpv_divisions=divisions,
            now=datetime.now(UTC),
        )
        return {
            "count": len(items),
            "top": [
                {"pub_no": i["pub_no"], "title": i["title"], "fit": i["fit"]} for i in items[:3]
            ],
        }

    @router.post("", status_code=202)
    def subscribe(
        request: Request, body: SubscribeRequest, session: Session = Depends(get_session)
    ) -> dict[str, str]:
        email = body.email.strip().lower()
        if not EMAIL_RE.match(email):
            raise HTTPException(422, "Neispravna e-adresa.")
        if not body.consent:
            raise HTTPException(422, "Potrebna je privola za slanje obavijesti.")
        oib = body.oib.strip() if body.oib else None
        query = body.query.strip() if body.query and body.query.strip() else None
        if oib is not None and not is_valid_oib(oib):
            raise HTTPException(422, "Neispravan OIB.")
        if oib is None and query is None:
            raise HTTPException(422, "Navedite OIB tvrtke ili opis pretrage.")
        county_codes = _check_counties(body.counties)
        wait = max(
            ip_limit.check(request.client.host if request.client else "unknown"),
            email_limit.check(email),
        )
        if wait > 0:
            raise HTTPException(
                429,
                "Previše pokušaja pretplate. Pokušajte ponovno kasnije.",
                headers={"Retry-After": str(int(wait))},
            )
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
        text = consent_text(body.frequency, body.min_fit)
        sub = existing or Subscription(
            email=email,
            oib=oib,
            query=query,
            confirmed=False,
            token_hash="pending",  # noqa: S106 - placeholder, replaced right below
            consent_text=text,
        )
        sub.min_fit = body.min_fit
        sub.min_value_eur = body.min_value_eur  # type: ignore[assignment]
        sub.counties = county_codes
        sub.cpv_divisions = sorted(set(body.cpv_divisions))
        sub.frequency = body.frequency
        sub.paused = False
        sub.consent_text = text
        if existing is None:
            session.add(sub)
            session.flush()
        token = make_confirm_token(sub.id)
        sub.token_hash = hash_token(token)
        session.commit()
        try:
            send_confirmation(settings, email, token, text)
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
        when = (
            "Prva obavijest stiže čim se pojavi natječaj koji dosegne vaš prag (provjera svako jutro u 7:00)."
            if sub.frequency == "daily"
            else "Prvi pregled stiže sljedeći ponedjeljak u 7:00."
        )
        return {"detail": f"Pretplata je potvrđena. {when}"}

    @router.get("/settings")
    def get_settings(token: str, session: Session = Depends(get_session)) -> dict[str, Any]:
        sub = _sub_for(token, session)
        excluded = len(
            session.scalars(
                select(AlertExclusion.id).where(AlertExclusion.subscription_id == sub.id)
            ).all()
        )
        return _prefs_payload(sub, excluded)

    @router.put("/settings")
    def put_settings(
        token: str, body: SettingsUpdate, session: Session = Depends(get_session)
    ) -> dict[str, Any]:
        sub = _sub_for(token, session)
        if body.min_fit is not None:
            sub.min_fit = body.min_fit
        if body.clear_min_value:
            sub.min_value_eur = None
        elif body.min_value_eur is not None:
            sub.min_value_eur = body.min_value_eur  # type: ignore[assignment]
        if body.counties is not None:
            sub.counties = _check_counties(body.counties)
        if body.cpv_divisions is not None:
            sub.cpv_divisions = sorted(set(body.cpv_divisions))
        if body.frequency is not None:
            sub.frequency = body.frequency
        if body.paused is not None:
            sub.paused = body.paused
        session.commit()
        excluded = len(
            session.scalars(
                select(AlertExclusion.id).where(AlertExclusion.subscription_id == sub.id)
            ).all()
        )
        return _prefs_payload(sub, excluded)

    @router.post("/exclude")
    def exclude(
        token: str, body: ExcludeRequest, session: Session = Depends(get_session)
    ) -> dict[str, str]:
        """ "Ne zanima me": this procedure is not offered again and its CPV group is down-ranked."""
        sub = _sub_for(token, session)
        notice = session.get(Notice, body.pub_no)
        group = notice.cpv_main[:3] if notice and notice.cpv_main else None
        already = session.scalars(
            select(AlertExclusion).where(
                AlertExclusion.subscription_id == sub.id, AlertExclusion.pub_no == body.pub_no
            )
        ).first()
        if already is None:
            session.add(AlertExclusion(subscription_id=sub.id, pub_no=body.pub_no, cpv_group=group))
            session.commit()
        return {"detail": "Zabilježeno: slični natječaji bit će rjeđi u obavijestima."}

    @router.delete("")
    def unsubscribe(token: str, session: Session = Depends(get_session)) -> dict[str, str]:
        sub_id = parse_unsub_token(token, settings)
        if sub_id is None:
            raise HTTPException(404, "Poveznica za odjavu nije valjana.")
        session.execute(delete(Subscription).where(Subscription.id == sub_id))
        session.commit()
        return {"detail": "Pretplata je otkazana i e-adresa je obrisana."}

    return router


# ------------------------------------------------------------------------------------ alert logic


def qualifying(
    session: Session,
    engine: MatchEngine,
    *,
    profile: Any,
    min_fit: float,
    min_value_eur: float | None = None,
    counties_codes: list[int] | None = None,
    cpv_divisions: list[str] | None = None,
    hidden: set[str] | None = None,
    dislike_groups: set[str] | None = None,
    now: datetime,
    cfg: FitConfig | None = None,
) -> list[dict[str, Any]]:
    """Open notices whose fit is at least ``min_fit`` (inclusive), best first, one per procedure."""
    if not profile.activities:
        return []
    by_code = {c.code: c.nuts3 for c in counties()}
    nuts3 = {by_code[c] for c in counties_codes or [] if c in by_code} or None
    items = engine.match(
        session,
        activities=profile.activities,
        company_nuts3=profile.nuts3,
        ranked_divisions=profile.ranked_divisions,
        ranked_groups=profile.ranked_groups,
        counties_nuts3=nuts3,
        cpv_divisions=set(cpv_divisions) if cpv_divisions else None,
        value_min=min_value_eur,
        hidden=hidden,
        dislike_groups=dislike_groups,
        group_lots=True,
        limit=1000,
        now=now,
        cfg=cfg or load_fit_config(),
    )
    return [i for i in items if i["fit"] >= min_fit - 1e-9]


def alert_items_for(
    session: Session,
    engine: MatchEngine,
    sub: Subscription,
    encode: Any,
    *,
    now: datetime,
) -> list[dict[str, Any]]:
    """Notices to e-mail to ``sub`` now (not sent before, not excluded), at most ``ALERT_CAP``."""
    try:
        profile = build_profile_full(session, oib=sub.oib, q=sub.query, encode=encode)
    except CompanyNotLoaded:
        return []
    sent = set(session.scalars(select(AlertSent.pub_no).where(AlertSent.subscription_id == sub.id)))
    excluded = list(
        session.execute(
            select(AlertExclusion.pub_no, AlertExclusion.cpv_group).where(
                AlertExclusion.subscription_id == sub.id
            )
        )
    )
    hidden = sent | {p for p, _ in excluded if p}
    dislike = {g for _, g in excluded if g}
    items = qualifying(
        session,
        engine,
        profile=profile,
        min_fit=sub.min_fit,
        min_value_eur=float(sub.min_value_eur) if sub.min_value_eur is not None else None,
        counties_codes=[int(c) for c in sub.counties or []],
        cpv_divisions=[str(d) for d in sub.cpv_divisions or []],
        hidden=hidden,
        dislike_groups=dislike,
        now=now,
    )
    return items[:ALERT_CAP]


def explain_item(item: dict[str, Any]) -> list[str]:
    """Plain-Croatian reasons ("Zašto?") for the e-mail, from the fit components."""
    comp = item["components"]
    reasons = [
        f"Opis nabave sličan je vašoj djelatnosti „{item['best_activity']['label']}” "
        f"(sličnost {round(comp['S'] * 100)} %)."
    ]
    label = item.get("cpv_division_label") or item.get("cpv_division")
    if comp["C"] >= 1:
        reasons.append(f"CPV područje ({label}) među vama najbližima.")
    elif comp["C"] > 0:
        reasons.append(f"CPV područje ({label}) djelomično odgovara vašim djelatnostima.")
    if item.get("signals", {}).get("cpv_group_match"):
        reasons.append("Podudara se i uža CPV skupina.")
    if comp["G"] >= 1:
        reasons.append("Naručitelj je u vašoj županiji.")
    elif comp["G"] >= 0.5 and item.get("county"):
        reasons.append(f"Naručitelj je u vašoj regiji ({item['county']}).")
    if item.get("days_left") is not None:
        reasons.append(f"Rok za ponude je za {round(item['days_left'])} dana.")
    return reasons


def send_alerts(
    session: Session,
    settings: NabavaSettings,
    engine: MatchEngine,
    encode: Any,
    *,
    frequency: Frequency = "daily",
    dry_run: bool = False,
    now: datetime | None = None,
) -> dict[str, int]:
    """Send threshold alerts (``daily``) or the weekly summary (``weekly``) to confirmed, unpaused
    subscriptions that have qualifying notices. One e-mail per subscriber per run."""
    now = now or datetime.now(UTC)
    env = make_template_env(TEMPLATES)
    sent = skipped = notices = 0
    subs = session.scalars(
        select(Subscription).where(
            Subscription.confirmed.is_(True),
            Subscription.paused.is_(False),
            Subscription.frequency == frequency,
        )
    ).all()
    for sub in subs:
        items = alert_items_for(session, engine, sub, encode, now=now)
        if not items:
            skipped += 1
            continue
        for it in items:
            it["reasons"] = explain_item(it)
        ctx = {
            "items": items,
            "frequency": frequency,
            "threshold": round(sub.min_fit * 100),
            "base": settings.public_base_url.rstrip("/"),
            "links": _links(
                settings,
                unsub=make_unsub_token(sub.id, settings),
                prefs=make_settings_token(sub.id, settings),
            ),
        }
        subject = (
            f"Birokratko: {len(items)} novih natječaja iznad vašeg praga"
            if frequency == "daily"
            else f"Birokratko: tjedni pregled, {len(items)} natječaja"
        )
        if not dry_run:
            send_email(
                sub.email,
                subject,
                render_email(env, "alert.html.j2", **ctx),
                render_email(env, "alert.txt.j2", **ctx),
                settings=settings,
            )
            for it in items:
                session.add(AlertSent(subscription_id=sub.id, pub_no=it["pub_no"], fit=it["fit"]))
            sub.last_sent_at = now
            session.commit()
        sent += 1
        notices += len(items)
    return {
        "sent": sent,
        "notices": notices,
        "skipped_no_new_matches": skipped,
        "dry_run": int(dry_run),
    }


def send_digests(
    session: Session,
    settings: NabavaSettings,
    engine: MatchEngine,
    encode: Any,
    *,
    dry_run: bool = False,
) -> dict[str, int]:
    """The weekly summary (cron: Monday 07:00) for subscriptions with ``frequency = weekly``."""
    return send_alerts(session, settings, engine, encode, frequency="weekly", dry_run=dry_run)
