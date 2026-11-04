"""End-to-end API tests on a small database seeded from the recorded real fixtures.

Seed: two real TED competition notices (2026-11-04) and the real Sudreg subject KOESTLIN d.d. (food
producer) with the NKD activities and labels from its recorded ``detalji_subjekta`` response. The real
e5 model embeds the texts, so the ranking assertions are semantic, not hard-coded.
"""

from __future__ import annotations

import json
import threading
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, sessionmaker

from nabavaradar_api.app import create_nabava_app
from nabavaradar_api.company import store_company
from nabavaradar_api.db import Calibration, Nkd, Notice
from nabavaradar_api.ingest.embed import embed_nkd, embed_notices
from nabavaradar_api.ingest.ted import upsert_notices
from nabavaradar_api.ingest.ted_parse import parse_notice
from nabavaradar_api.settings import NabavaSettings
from nabavaradar_api.subscriptions import make_router as subscriptions_router
from nabavaradar_api.sudreg.client import SlidingWindowLimiter, SudregClient
from nabavaradar_api.sudreg.parse import parse_detail
from opendata_core.db import make_engine, make_session_dependency

pytestmark = pytest.mark.db

FIX = Path(__file__).parent / "fixtures"
NOW = datetime(2026, 11, 4, 12, 0, tzinfo=UTC)  # the fixtures were recorded on this day
DIGEST_NOW = datetime(
    2026, 10, 24, 12, 0, tzinfo=UTC
)  # within 7 days of their publication (2026-10-20)
OIB = "92803032010"  # KOESTLIN d.d. (Sudreg test snapshot)
FOOD_TENDER = "722712-2026"  # enteral nutrition (hospital food)
MACHINE_TENDER = "722793-2026"  # spare parts and servicing of construction machines


def settings_for(url: str, **over: object) -> NabavaSettings:
    return NabavaSettings(
        _env_file=None,
        database_url=url,
        contact_email="test@example.hr",
        sudreg_token_url="https://sudreg.test/api/oauth/token",
        sudreg_base_url="https://sudreg.test/api/javni",
        smtp_host="127.0.0.1",
        smtp_port=1,  # nothing listens: mails fail loudly in tests that should not send
        **over,
    )


def detail_body() -> dict:
    return json.loads(
        (FIX / "sudreg" / "2026-11-04_detalji_subjekta_oib92803032010.json").read_text(
            encoding="utf-8"
        )
    )["body"]


@pytest.fixture(scope="module")
def factory(test_db_url: str) -> sessionmaker[Session]:
    settings = settings_for(test_db_url)
    sf = sessionmaker(make_engine(settings), expire_on_commit=False)
    with sf() as s:
        # notices from the two recorded TED competition responses
        raw = json.loads(
            (FIX / "ted" / "2026-11-04_search_competition.json").read_text(encoding="utf-8")
        )
        upsert_notices(s, [parse_notice(n, "competition") for n in raw["response"]["notices"]])
        s.commit()
        # the company and the real NKD labels of its recorded activities
        body = detail_body()
        record = parse_detail(body)
        assert record is not None
        record.activities = [
            a for a in record.activities if a[1] != "NKD 2007"
        ]  # label of 10.72 is not in the fixture
        labels = {
            (
                i["nacionalna_klasifikacija_djelatnosti"]["sifra"],
                i["nacionalna_klasifikacija_djelatnosti"]["verzija"],
            ): i["nacionalna_klasifikacija_djelatnosti"]["puni_naziv"]
            for i in body["predmeti_poslovanja"]
            if "nacionalna_klasifikacija_djelatnosti" in i  # some entries are free text only
        }
        for n, (code, version, _main) in enumerate(record.activities, start=1):
            s.add(Nkd(code=code, version=version, sudreg_id=n, label_hr=labels[(code, version)]))
        s.commit()
        store_company(s, record)
        embed_nkd(s)
        embed_notices(s)
        s.add(Calibration(key="activity_notice_cosine", value={"p5": 0.70, "p95": 0.85}))
        s.commit()
    return sf


def make_client(url: str, factory: sessionmaker[Session], **settings_over: object) -> TestClient:
    settings = settings_for(url, **settings_over)
    engine = make_engine(settings)
    app = create_nabava_app(
        settings,
        make_session_dependency(engine),
        factory,
        extra_routers=[subscriptions_router(make_session_dependency(engine), settings)],
        lookup_client=settings_over.get("_client"),  # type: ignore[arg-type]
    )
    return TestClient(app)


def test_migrations_created_tables_and_hnsw_indexes(factory: sessionmaker[Session]) -> None:
    with factory() as s:
        tables = {
            r[0]
            for r in s.execute(text("select tablename from pg_tables where schemaname='public'"))
        }
        assert {
            "company",
            "company_activity",
            "nkd",
            "cpv",
            "notice",
            "award",
            "crosswalk",
            "competition_stat",
            "subscription",
            "data_source",
            "ingestion_run",
        } <= tables
        indexes = {
            r[0]
            for r in s.execute(
                text("select indexname from pg_indexes where indexdef ilike '%hnsw%'")
            )
        }
        assert {
            "idx_nkd_embedding_hnsw",
            "idx_cpv_embedding_hnsw",
            "idx_notice_embedding_hnsw",
        } <= indexes


def test_seed_is_embedded(factory: sessionmaker[Session]) -> None:
    with factory() as s:
        assert (
            s.scalar(select(func.count()).select_from(Notice).where(Notice.embedding.is_not(None)))
            == 2
        )
        assert (
            s.scalar(select(func.count()).select_from(Nkd).where(Nkd.embedding.is_not(None))) >= 5
        )


def test_match_ranks_the_food_tender_above_the_machinery_tender(
    test_db_url: str, factory: sessionmaker[Session]
) -> None:
    from nabavaradar_api.match import MatchEngine, build_profile
    from opendata_core import semantic

    with factory() as s:
        activities, nuts3, ranked = build_profile(
            s, oib=OIB, q=None, encode=semantic.encode_queries
        )
        assert nuts3 == "HR021"  # Bjelovarsko-bilogorska
        assert len(activities) >= 5
        items = MatchEngine().match(
            s, activities=activities, company_nuts3=nuts3, ranked_divisions=ranked, now=NOW
        )
    assert [i["pub_no"] for i in items] == [FOOD_TENDER, MACHINE_TENDER]
    food, machine = items
    assert food["fit"] > machine["fit"]
    assert food["similarity"] > machine["similarity"]
    for it in items:
        assert set(it["components"]) == {"S", "C", "G", "T"}
        assert all(0.0 <= v <= 1.0 for v in it["components"].values())
        assert it["components"]["C"] == 0.0  # no crosswalk seeded
        assert it["competition"]["n"] == 0
        assert it["competition"]["flag"] is False
        assert it["url_html"].startswith("https://ted.europa.eu/")
    assert food["days_left"] == pytest.approx(15.9, abs=0.1)  # 2026-11-20 09:00 +02:00 from NOW
    assert food["nuts3"] == "HR035" or food["nuts3"] is None
    # G: the buyer (KBC Split, HR035) is in another region (HR03) than the company (HR02)
    assert food["components"]["G"] in (0.2, 0.5)
    # T: more than 15 days left for the food tender, so the time component is full
    assert food["components"]["T"] == 1.0


def test_api_company_and_match_and_validation(
    test_db_url: str, factory: sessionmaker[Session]
) -> None:
    with make_client(test_db_url, factory) as client:
        r = client.get(f"/api/v1/company/{OIB}")
        assert r.status_code == 200
        body = r.json()
        assert body["name"].startswith("KOESTLIN")
        assert body["county"]["nuts3"] == "HR021"
        assert body["source"]["environment"] == "production"
        assert "osobe" not in json.dumps(body).lower()

        assert (
            client.get("/api/v1/company/12345678901").status_code == 422
        )  # checksum, no external call
        assert client.get("/api/v1/match").status_code == 422  # neither oib nor q
        assert client.get("/api/v1/match", params={"oib": "12345678901"}).status_code == 422
        assert client.get("/api/v1/match", params={"oib": OIB, "county": 99}).status_code == 422
        assert (
            client.get("/api/v1/match", params={"oib": "61817894937"}).status_code == 404
        )  # valid, not loaded

        ok = client.get("/api/v1/match", params={"oib": OIB, "limit": 5})
        assert ok.status_code == 200
        assert {i["pub_no"] for i in ok.json()} <= {FOOD_TENDER, MACHINE_TENDER}
        assert (
            client.get("/api/v1/validation").status_code == 404
        )  # not run on the scratch database
        assert client.get("/health").json()["db"] == "ok"


def test_api_notice_and_competition_validation(
    test_db_url: str, factory: sessionmaker[Session]
) -> None:
    with make_client(test_db_url, factory) as client:
        n = client.get(f"/api/v1/notices/{FOOD_TENDER}")
        assert n.status_code == 200
        assert n.json()["cpv_main"] == "33692300"
        assert n.json()["n_lots"] == 3
        assert client.get("/api/v1/notices/000000-0000").status_code == 404
        assert client.get("/api/v1/competition", params={"cpv": "abc"}).status_code == 422
        assert (
            client.get("/api/v1/competition", params={"cpv": "45", "nuts2": "HR99"}).status_code
            == 422
        )
        assert client.get("/api/v1/competition", params={"cpv": "33692300-6"}).status_code == 200
        for bad in (
            {},
            {"text": "x", "cpv": "45"},
            {"cpv": "4"},
            {"text": "x" * 2001},
            {"cpv": "45", "county": 99},
        ):
            assert client.post("/api/v1/sounding", json=bad).status_code == 422, bad


def test_unknown_company_without_credentials_is_a_clear_503(
    test_db_url: str, factory: sessionmaker[Session]
) -> None:
    with make_client(test_db_url, factory) as client:
        r = client.get("/api/v1/company/61817894937")
        assert r.status_code == 503
        assert "SUDREG_CLIENT_ID" in r.json()["detail"]


def test_live_lookup_over_the_rate_limit_returns_202_then_200(
    test_db_url: str, factory: sessionmaker[Session]
) -> None:
    """Six lookups already used this minute: the seventh waits in the queue; the API answers 202."""
    other = detail_body() | {"oib": 76860791838, "potpuni_oib": "76860791838", "mbs": 10000074}
    other["tvrtka"] = {"ime": "ZAVOD ZA JAVNO ZDRAVSTVO SVETI ROK VIROVITIČKO-PODRAVSKE ŽUPANIJE"}
    other["sjediste"] = {"sifra_zupanije": 10, "naziv_zupanije": "Virovitičko-podravska županija"}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/oauth/token"):
            return httpx.Response(
                200, json={"access_token": "t", "token_type": "bearer", "expires_in": 3600}
            )
        return httpx.Response(
            200, json=other, headers={"x-snapshot-id": "1", "x-timestamp": "2024-06-16T20:57:57"}
        )

    gate = threading.Event()
    limiter = SlidingWindowLimiter()
    for _ in range(6):
        limiter.reserve()
    settings = settings_for(
        test_db_url, sudreg_client_id="id..", sudreg_client_secret=SecretStr("secret..")
    )
    sudreg = SudregClient(
        settings,
        http=httpx.Client(transport=httpx.MockTransport(handler)),
        sleep=lambda _s: gate.wait(30),
        limiter=limiter,
    )
    with make_client(
        test_db_url,
        factory,
        sudreg_client_id="id..",
        sudreg_client_secret=SecretStr("secret.."),
        _client=sudreg,
    ) as client:
        r = client.get("/api/v1/company/76860791838")
        assert r.status_code == 202
        assert int(r.headers["retry-after"]) >= 5
        assert r.json()["status"] == "queued"
        gate.set()  # the rate-limit window "expires": the worker completes the lookup
        for _ in range(40):
            again = client.get("/api/v1/company/76860791838")
            if again.status_code == 200:
                break
            threading.Event().wait(0.5)
        assert again.status_code == 200
        assert again.json()["name"].startswith("ZAVOD ZA JAVNO ZDRAVSTVO")
        assert again.json()["county"]["nuts3"] == "HR022"


def test_match_rate_limit_is_30_per_minute_per_ip(
    test_db_url: str, factory: sessionmaker[Session]
) -> None:
    with make_client(test_db_url, factory, rate_limit="1000/minute") as client:
        codes = [
            client.get("/api/v1/match", params={"oib": OIB, "limit": 1}).status_code
            for _ in range(32)
        ]
    assert codes[:30] == [200] * 30
    assert set(codes[30:]) == {429}


def test_subscription_double_opt_in_and_unsubscribe(
    test_db_url: str, factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    from nabavaradar_api import subscriptions as subs

    sent: list[tuple[str, str]] = []
    monkeypatch.setattr(
        subs, "send_confirmation", lambda _settings, email, token: sent.append((email, token))
    )
    with make_client(test_db_url, factory) as client:

        def post(**kw):
            return client.post(
                "/api/v1/subscriptions",
                json={"email": "ana@example.hr", "oib": OIB, "consent": True} | kw,
            )  # noqa: E731

        assert post(consent=False).status_code == 422  # consent is required
        assert post(email="not-an-email").status_code == 422
        assert post(oib="12345678901").status_code == 422
        assert post(oib=None).status_code == 422  # nothing to subscribe to
        r = post()
        assert r.status_code == 202
        assert sent
        email, token = sent[-1]
        with factory() as s:
            row = s.execute(
                text(
                    "select confirmed, token_hash, consent_text from subscription where email='ana@example.hr'"
                )
            ).one()
            assert row.confirmed is False
            assert token not in row.token_hash
            assert len(row.token_hash) == 64
            assert "ponedjeljkom" in row.consent_text
        assert (
            client.get("/api/v1/subscriptions/confirm", params={"token": "1.nope"}).status_code
            == 404
        )
        assert (
            client.get("/api/v1/subscriptions/confirm", params={"token": token}).status_code == 200
        )
        with factory() as s:
            assert (
                s.execute(
                    text("select confirmed from subscription where email='ana@example.hr'")
                ).scalar()
                is True
            )
        again = post()  # an already confirmed address is not revealed
        assert again.status_code == 202
        assert len(sent) == 1

        settings = settings_for(test_db_url)
        sub_id = int(token.split(".")[0])
        good = subs.make_unsub_token(sub_id, settings)
        assert (
            client.delete("/api/v1/subscriptions", params={"token": good + "0"}).status_code == 404
        )
        assert client.delete("/api/v1/subscriptions", params={"token": "abc"}).status_code == 404
        assert client.delete("/api/v1/subscriptions", params={"token": good}).status_code == 200
        with factory() as s:
            assert (
                s.scalar(text("select count(*) from subscription where email='ana@example.hr'"))
                == 0
            )


def test_digest_picks_new_matches_and_marks_sent(
    test_db_url: str, factory: sessionmaker[Session], monkeypatch: pytest.MonkeyPatch
) -> None:
    from nabavaradar_api import subscriptions as subs
    from nabavaradar_api.db import Subscription
    from nabavaradar_api.match import MatchEngine
    from opendata_core import semantic

    mails: list[tuple[str, str]] = []
    monkeypatch.setattr(
        subs, "send_email", lambda to, subject, html, text_, settings: mails.append((to, subject))
    )
    settings = settings_for(test_db_url)
    with factory() as s:
        sub = Subscription(
            email="bor@example.hr",
            oib=OIB,
            query=None,
            confirmed=True,
            token_hash="h" * 64,
            consent_text="x",
        )
        s.add(sub)
        s.commit()
        # the fixtures were published 2026-10-20: a "now" within 7 days of that finds them (first digest
        # looks back 7 days), and their deadlines (Nov 17-20) are still in the future
        monkeypatch.setattr(
            subs, "datetime", type("D", (), {"now": staticmethod(lambda tz=None: DIGEST_NOW)})
        )
        out = subs.send_digests(s, settings, MatchEngine(), semantic.encode_queries, dry_run=False)
        assert out["sent"] == 1
        assert mails
        assert mails[0][0] == "bor@example.hr"
        assert "novih natječaja" in mails[0][1]
        s.refresh(sub)
        assert sub.last_sent_at is not None
        # nothing new since the last digest -> nothing is sent
        mails.clear()
        out2 = subs.send_digests(s, settings, MatchEngine(), semantic.encode_queries, dry_run=False)
        assert out2["sent"] == 0
        assert not mails


def test_open_index_excludes_expired_and_stale_undated_notices(
    factory: sessionmaker[Session],
) -> None:
    """Expired notices are never open; a notice without any deadline stays only while it is recent."""
    from nabavaradar_api.match import load_index

    with factory() as s:
        before = {r["pub_no"] for r in load_index(s, NOW).rows}
        assert before == {FOOD_TENDER, MACHINE_TENDER}
        # 1. the machinery tender is undated and was published long ago -> dropped
        s.execute(
            text(
                "update notice set deadline = null, pub_date = date '2025-01-10' where pub_no = :p"
            ),
            {"p": MACHINE_TENDER},
        )
        s.commit()
        assert {r["pub_no"] for r in load_index(s, NOW).rows} == {FOOD_TENDER}
        # 2. undated but recent -> kept (neutral T)
        s.execute(
            text("update notice set pub_date = date '2026-10-20' where pub_no = :p"),
            {"p": MACHINE_TENDER},
        )
        s.commit()
        assert {r["pub_no"] for r in load_index(s, NOW).rows} == {FOOD_TENDER, MACHINE_TENDER}
        # 3. a deadline in the past -> expired
        s.execute(
            text(
                "update notice set deadline = timestamptz '2026-11-01 10:00+01' where pub_no = :p"
            ),
            {"p": MACHINE_TENDER},
        )
        s.commit()
        assert {r["pub_no"] for r in load_index(s, NOW).rows} == {FOOD_TENDER}
        # restore the recorded values for the other tests
        s.execute(
            text(
                "update notice set deadline = timestamptz '2026-11-17 12:00+02', pub_date = date '2026-10-20' where pub_no = :p"
            ),
            {"p": MACHINE_TENDER},
        )
        s.commit()
