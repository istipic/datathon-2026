"""TED parsing on the recorded real search responses (tests/fixtures/ted)."""

from __future__ import annotations

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from nabavaradar_api.ingest import ted_parse as tp

FIX = Path(__file__).parent / "fixtures" / "ted"


def load(name: str) -> dict[str, dict]:
    notices = json.loads((FIX / name).read_text(encoding="utf-8"))["response"]["notices"]
    return {n["publication-number"]: n for n in notices}


@pytest.fixture(scope="module")
def competition() -> dict[str, dict]:
    return load("2026-11-04_search_competition.json")


@pytest.fixture(scope="module")
def result() -> dict[str, dict]:
    return load("2026-11-04_search_result.json")


def test_competition_notice_single_buyer_three_lots(competition) -> None:
    p = tp.parse_notice(competition["722712-2026"], "competition")
    r = p.row
    assert r["type"] == "competition"
    assert r["notice_type"] == "cn-standard"
    assert r["pub_date"] == date(2026, 10, 20)
    assert r["buyer_name"] == "KLINIČKI BOLNIČKI CENTAR SPLIT"
    assert r["buyer_nuts"] is None or r["buyer_nuts"].startswith("HR")
    assert r["place_nuts"] == "HR035"
    assert r["cpv_codes"] == ["33692300"]
    assert r["cpv_main"] == "33692300"
    assert r["title"] == "Enteralna prehrana"
    assert "Grupa 1" in r["description"]
    assert r["n_lots"] == 3
    assert r["value_eur"] == Decimal("580952")
    assert r["currency"] == "EUR"
    assert r["url_html"].startswith("https://ted.europa.eu/hr/notice/-/detail/722712-2026")
    assert r["url_pdf"].endswith("/722712-2026/pdf")
    assert p.awards == []
    # Croatian text kept, the other 22 languages dropped from the stored raw
    assert set(r["raw"]["notice-title"]) <= {"hrv", "eng"}


def test_competition_deadline_is_timezone_aware_and_combines_date_and_time(competition) -> None:
    r = tp.parse_notice(competition["722712-2026"], "competition").row
    assert r["deadline"].isoformat() == "2026-11-20T09:00:00+02:00"


def test_competition_notice_many_lots_uses_procedure_value(competition) -> None:
    r = tp.parse_notice(competition["722793-2026"], "competition").row
    assert r["n_lots"] == 14
    assert r["cpv_main"] == "43600000"
    assert r["place_nuts"] == "HR050"
    assert r["value_eur"] == Decimal("3793000")
    assert r["deadline"].isoformat() == "2026-11-17T12:00:00+02:00"


def test_result_notice_multi_lot_aligns_winners_with_lots_and_submissions(result) -> None:
    p = tp.parse_notice(result["722709-2026"], "result")
    assert p.row["type"] == "result"
    assert p.row["deadline"] is None
    assert p.row["value_eur"] is None
    by_lot = {a["lot_id"]: a for a in p.awards}
    assert len(p.awards) == 8
    assert set(by_lot) == {f"LOT-000{i}" for i in range(1, 9)}
    # winners follow tender-lot-identifier (LOT-1, 2, 3, 7), NOT the order of the lots
    assert by_lot["LOT-0001"]["winner_name"] == "SANOL H d.o.o."
    assert by_lot["LOT-0001"]["winner_national_id"] == "65605433360"
    assert by_lot["LOT-0002"]["winner_national_id"] == "70869514300"
    assert by_lot["LOT-0003"]["winner_name"] == "SRIJEM d.o.o."
    assert by_lot["LOT-0007"]["winner_name"] == "MA-CO PLAST d.o.o."
    assert by_lot["LOT-0007"]["winner_national_id"] == "20765781286"
    # lots closed without a winner carry no winner row
    for lot in ("LOT-0004", "LOT-0005", "LOT-0006", "LOT-0008"):
        assert by_lot[lot]["lot_status"] == "clos-nw"
        assert by_lot[lot]["winner_name"] is None
    # number of tenders received per lot (the 'tenders' entry of every 5-value block)
    assert [by_lot[f"LOT-000{i}"]["received_submissions"] for i in range(1, 9)] == [
        2,
        5,
        2,
        3,
        3,
        3,
        2,
        2,
    ]


def test_result_notice_two_tenders_of_one_winner_share_one_identifier(result) -> None:
    p = tp.parse_notice(result["722770-2026"], "result")
    assert [a["winner_name"] for a in p.awards] == ["BINĐO d.o.o.", "BINĐO d.o.o."]
    assert [a["winner_national_id"] for a in p.awards] == ["49733628869", "49733628869"]
    assert [a["seq"] for a in p.awards] == [0, 1]
    assert {a["lot_id"] for a in p.awards} == {"LOT-0000"}
    assert p.awards[0]["received_submissions"] == 2


def test_received_per_lot_blocks() -> None:
    codes = ["tenders", "t-sme", "tenders", "t-sme", "tenders", "t-sme"]
    vals = ["3", "1", "1", "0", "7", "2"]
    assert tp.received_per_lot(codes, vals, 3) == [3, 1, 7]


def test_received_per_lot_unreliable_alignment_gives_none() -> None:
    codes = ["tenders", "t-sme", "tenders", "t-sme"]
    assert tp.received_per_lot(codes, ["1", "1", "2", "2"], 3) == [None, None, None]
    assert tp.received_per_lot(codes, ["1"], 2) == [None, None]
    assert tp.received_per_lot([], [], 2) == [None, None]


def test_winner_ids_mapping_rules() -> None:
    assert tp.winner_ids_per_tender(["A", "B"], ["1", "2"]) == ["1", "2"]
    assert tp.winner_ids_per_tender(["A", "A", "B"], ["1", "2"]) == ["1", "1", "2"]
    assert tp.winner_ids_per_tender(["A", "B", "C"], ["1"]) == [None, None, None]
    assert tp.winner_ids_per_tender([], ["1"]) == []


def test_legacy_notice_without_winner_fields_has_no_awards() -> None:
    """Real notice 674010-2023 (published before the eForms data reached the API): no winner data."""
    raw = json.loads(
        (FIX / "2026-11-04_result_legacy_674010-2023.json").read_text(encoding="utf-8")
    )
    assert "winner-identifier" not in raw
    assert "received-submissions-type-val" not in raw
    p = tp.parse_notice(raw, "result")
    assert p.awards == []
    assert p.row["pub_date"] == date(2023, 11, 7)
    assert p.row["buyer_name"]
    assert p.row["cpv_main"]


def test_helpers() -> None:
    assert tp.ml_first({"eng": ["x"], "hrv": ["y"]}) == "y"
    assert tp.ml_first({"eng": "x"}) == "x"
    assert tp.ml_first(None) is None
    assert tp.first_nuts3(["HRV", "HR035"]) == "HR035"
    assert tp.first_nuts3(["HRV"]) is None
    assert tp.parse_date("2026-07-07+02:00") == date(2026, 7, 7)
    assert tp.parse_date("garbage") is None
    assert tp.parse_decimal("12.5") == Decimal("12.5")
    assert tp.parse_decimal("x") is None


def test_result_lot_result_repeated_for_two_winners_gives_unique_award_keys() -> None:
    """Real notice 93705-2024: result-lot-identifier = [LOT-0000, LOT-0000] (two winners, one lot)."""
    raw = json.loads(
        (FIX / "2026-11-04_result_duplicate_lots_93705-2024.json").read_text(encoding="utf-8")
    )
    awards = tp.parse_notice(raw, "result").awards
    keys = [(a["pub_no"], a["lot_id"], a["seq"]) for a in awards]
    assert len(keys) == len(set(keys)) == 2
    assert [a["winner_national_id"] for a in awards] == ["79873237024", "69702906688"]
    assert [a["received_submissions"] for a in awards] == [10, 10]
    assert {a["lot_status"] for a in awards} == {"selec-w"}


def test_restricted_procedure_uses_the_request_to_participate_deadline() -> None:
    """Real notice 759307-2026: no tender deadline, only deadline-receipt-request-* (restricted procedure)."""
    raw = json.loads(
        (FIX / "2026-11-04_competition_restricted_759307-2026.json").read_text(encoding="utf-8")
    )
    assert "deadline-receipt-tender-date-lot" not in raw
    p = tp.parse_notice(raw, "competition")
    assert p.row["deadline"].isoformat() == "2026-11-06T14:00:00+01:00"
    assert tp.deadline_kind(raw) == "request"


def test_tender_deadline_wins_when_both_exist() -> None:
    raw = {
        "publication-number": "1-2026",
        "deadline-receipt-tender-date-lot": ["2026-12-01+01:00"],
        "deadline-receipt-tender-time-lot": ["10:00:00+01:00"],
        "deadline-receipt-request-date-lot": ["2026-11-01+01:00"],
        "deadline-receipt-request-time-lot": ["09:00:00+01:00"],
    }
    assert tp.notice_deadline(raw).isoformat() == "2026-12-01T10:00:00+01:00"
    assert tp.deadline_kind(raw) == "tender"
    assert tp.deadline_kind({}) is None
