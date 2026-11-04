"""Sudreg token, detalji_subjekta parsing, rate limiting and paginated reads (recorded fixtures)."""

from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest
import respx
from pydantic import SecretStr

from nabavaradar_api.settings import NabavaSettings
from nabavaradar_api.sudreg.client import (
    RateLimited,
    SlidingWindowLimiter,
    SudregAuthError,
    SudregClient,
    SudregNotFound,
)
from nabavaradar_api.sudreg.parse import (
    exclusion_reason,
    nkd_code_from_number,
    parse_detail,
)

FIX = Path(__file__).parent / "fixtures" / "sudreg"
TOKEN_URL = "https://sudreg.test/api/oauth/token"
BASE = "https://sudreg.test/api/javni"
OIB = "92803032010"


def settings() -> NabavaSettings:
    return NabavaSettings(
        _env_file=None,
        contact_email="test@example.hr",
        sudreg_client_id="id..",
        sudreg_client_secret=SecretStr("secret.."),
        sudreg_token_url=TOKEN_URL,
        sudreg_base_url=BASE,
    )


def detail_body() -> dict:
    return json.loads(
        (FIX / "2026-11-04_detalji_subjekta_oib92803032010.json").read_text(encoding="utf-8")
    )["body"]


class Clock:
    def __init__(self) -> None:
        self.t = 1000.0
        self.slept: list[float] = []

    def __call__(self) -> float:
        return self.t

    def sleep(self, s: float) -> None:
        self.slept.append(s)
        self.t += s


def token_json(ttl: int = 3600) -> dict:
    return {"access_token": "tok-123", "token_type": "bearer", "expires_in": ttl}


# ---------------------------------------------------------------------------- parsing


def test_nkd_number_to_code() -> None:
    assert nkd_code_from_number(1072) == "10.72"
    assert nkd_code_from_number("6201") == "62.01"
    assert nkd_code_from_number(107) == "01.07"  # leading zero lost by the numeric field


def test_parse_real_detail_fixture() -> None:
    rec = parse_detail(detail_body())
    assert rec is not None
    assert (rec.oib, rec.mbs) == (OIB, 10000162)
    assert rec.name.startswith("KOESTLIN")
    assert rec.status == 1
    assert (rec.county_code, rec.nuts3) == (7, "HR021")  # Bjelovarsko-bilogorska
    main = [a for a in rec.activities if a[2]]
    assert main == [("10.72", "NKD 2007", True)]
    assert ("15.8", "NKD 1994", False) in rec.activities
    assert len({(c, v) for c, v, _ in rec.activities}) == len(rec.activities)  # no duplicates


def test_parsed_record_holds_company_level_fields_only() -> None:
    rec = parse_detail(detail_body())
    assert rec is not None
    assert set(vars(rec)) == {
        "oib",
        "mbs",
        "name",
        "status",
        "county_code",
        "nuts3",
        "activities",
        "snapshot_id",
        "snapshot_at",
    }
    blob = json.dumps(detail_body()).lower()
    for forbidden in ("osobe", "funkcij", "osoba_rbr", "datum_rodjenja"):
        assert forbidden not in blob  # the fixture itself carries no person data


def test_invalid_oib_in_detail_is_rejected() -> None:
    body = detail_body() | {"oib": 92803032011, "potpuni_oib": "92803032011"}
    assert parse_detail(body) is None


def test_exclusion_rules() -> None:
    base = detail_body()
    assert exclusion_reason(base) is None
    sole = base | {
        "pravni_oblik": {"vrsta_pravnog_oblika": {"sifra": 6, "naziv": "trgovac pojedinac"}}
    }
    assert exclusion_reason(sole) == "sole_trader"
    assert exclusion_reason(base | {"stecajna_masa": 1}) == "estate"
    assert (
        exclusion_reason(base | {"postupak": {"postupak": {"znacenje": "Stečaj"}}})
        == "bankruptcy_or_liquidation"
    )
    assert exclusion_reason(base | {"postupak": 3}) == "bankruptcy_or_liquidation"
    assert exclusion_reason(base | {"postupak": 1}) is None


# ---------------------------------------------------------------------------- token


@respx.mock
def test_token_is_cached_until_expiry_and_uses_expires_in() -> None:
    clock = Clock()
    route = respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=token_json(3600)))
    client = SudregClient(settings(), http=httpx.Client(), clock=clock, sleep=clock.sleep)
    assert client.token() == "tok-123"
    assert client.token() == "tok-123"
    assert route.call_count == 1  # cached
    clock.t += 3600 - 61  # still before expiry minus the 60 s skew
    client.token()
    assert route.call_count == 1
    clock.t += 5  # now inside the skew window: refresh
    client.token()
    assert route.call_count == 2
    sent = route.calls.last.request
    assert sent.headers["authorization"].startswith("Basic ")
    assert b"grant_type=client_credentials" in sent.content


@respx.mock
def test_token_refused_raises_auth_error_without_leaking_secrets() -> None:
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(401, text="no"))
    client = SudregClient(settings(), http=httpx.Client())
    with pytest.raises(SudregAuthError) as exc:
        client.token()
    assert "secret" not in str(exc.value)


def test_missing_credentials_fail_fast() -> None:
    s = NabavaSettings(
        _env_file=None,
        contact_email="t@x.hr",
        sudreg_client_id="",
        sudreg_client_secret=SecretStr(""),
    )
    with pytest.raises(SudregAuthError):
        SudregClient(s, http=httpx.Client()).token()


# ---------------------------------------------------------------------------- rate limit


def test_limiter_defers_the_seventh_call_in_a_minute() -> None:
    clock = Clock()
    lim = SlidingWindowLimiter(clock=clock)
    waits = [lim.reserve() for _ in range(7)]
    assert waits[:6] == [0.0] * 6
    assert waits[6] == pytest.approx(60.0)  # the 7th has to wait for the first slot to expire
    clock.t += 30
    assert lim.peek() > 0
    clock.t += 31
    assert lim.peek() == 0


@respx.mock
def test_seventh_detalji_call_is_deferred_not_sent() -> None:
    clock = Clock()
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=token_json()))
    route = respx.get(f"{BASE}/detalji_subjekta").mock(
        return_value=httpx.Response(
            200,
            json=detail_body(),
            headers={"x-snapshot-id": "1", "x-timestamp": "2024-06-16T20:57:57"},
        )
    )
    client = SudregClient(settings(), http=httpx.Client(), clock=clock, sleep=clock.sleep)
    for _ in range(6):
        body = client.detalji_subjekta(OIB)
        assert body["_snapshot_id"] == "1"
    with pytest.raises(RateLimited) as exc:
        client.detalji_subjekta(OIB)  # 7th within the minute
    assert exc.value.retry_after == pytest.approx(60.0)
    assert route.call_count == 6  # nothing was sent for the deferred call
    clock.t += 61
    client.detalji_subjekta(OIB)  # allowed again
    assert route.call_count == 7


@respx.mock
def test_seventh_call_waits_when_blocking() -> None:
    clock = Clock()
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=token_json()))
    respx.get(f"{BASE}/detalji_subjekta").mock(return_value=httpx.Response(200, json=detail_body()))
    client = SudregClient(settings(), http=httpx.Client(), clock=clock, sleep=clock.sleep)
    for _ in range(7):
        client.detalji_subjekta(OIB, wait=True)
    assert clock.slept
    assert clock.slept[-1] == pytest.approx(60.0)


# ---------------------------------------------------------------------------- errors, paging


@respx.mock
def test_data_call_401_means_unverified_account() -> None:
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=token_json()))
    respx.get(f"{BASE}/snapshots").mock(
        return_value=httpx.Response(401, json={"code": "Unauthorized"})
    )
    with pytest.raises(SudregAuthError, match="not verified"):
        SudregClient(settings(), http=httpx.Client()).snapshots()


@respx.mock
def test_unknown_oib_is_not_found() -> None:
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=token_json()))
    respx.get(f"{BASE}/detalji_subjekta").mock(
        return_value=httpx.Response(
            400,
            json={
                "error_code": 505,
                "error_message": "Vaš zahtjev nije vratio ni jedan redak",
                "log_id": 1,
            },
        )
    )
    with pytest.raises(SudregNotFound):
        SudregClient(settings(), http=httpx.Client()).detalji_subjekta(OIB)


def real_rows() -> list[dict]:
    return json.loads((FIX / "2026-11-04_subjekti_first3.json").read_text(encoding="utf-8"))["body"]


@respx.mock
def test_bulk_table_is_pinned_to_one_snapshot_and_pages_until_total() -> None:
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=token_json()))
    rows = real_rows()  # three real `subjekti` rows, served as pages of 2 + 1
    pages = {0: rows[:2], 2: rows[2:]}

    def handler(request: httpx.Request) -> httpx.Response:
        offset = int(request.url.params["offset"])
        assert request.url.params["snapshot_id"] == "7"
        return httpx.Response(200, json=pages[offset], headers={"x-total-count": "3"})

    route = respx.get(f"{BASE}/subjekti").mock(side_effect=handler)
    got = [
        r["mbs"]
        for page in SudregClient(settings(), http=httpx.Client()).table("subjekti", 7, page_size=2)
        for r in page
    ]
    assert got == [r["mbs"] for r in rows]
    assert route.call_count == 2


@respx.mock
def test_snapshots_sorted_freshest_first() -> None:
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json=token_json()))
    real = json.loads((FIX / "2026-11-04_snapshots.json").read_text(encoding="utf-8"))["body"]
    older = {**real[0], "id": 0, "staleness": 2}  # the real row, plus an older copy of it
    respx.get(f"{BASE}/snapshots").mock(return_value=httpx.Response(200, json=[older, real[0]]))
    snaps = SudregClient(settings(), http=httpx.Client()).snapshots()
    assert [s.id for s in snaps] == [real[0]["id"], 0]
    assert snaps[0].timestamp.startswith("2024-06-16")
