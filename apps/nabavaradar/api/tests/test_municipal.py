"""Municipal contract registers: header fuzzy mapping, cell parsing, and two real CKAN files."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from nabavaradar_api.ingest.municipal import (
    clean_cpv,
    extract_rows,
    find_header,
    is_company_name,
    map_headers,
    mapped_groups,
    normalise_header,
    parse_amount,
    parse_date,
    phrase_score,
    read_table,
)

FIX = Path(__file__).parent / "fixtures" / "ckan"
CSV = FIX / "2026-11-04_registar_ugovora_dugo_selo.csv"
XLSX = FIX / "2026-11-04_registar_ugovora_kravarsko.xlsx"


def test_normalise_header_strips_diacritics_and_punctuation() -> None:
    assert normalise_header("Iznos s PDV-om ") == "iznos s pdv om"
    assert normalise_header("Izvođač") == "izvodac"
    assert normalise_header("Naručitelj\n(naziv)") == "narucitelj naziv"
    assert normalise_header(None) == ""


def test_single_word_phrases_match_only_identically() -> None:
    assert phrase_score("datum", "datum") == 100
    assert phrase_score("datum izvrsenja", "datum") == 0
    assert phrase_score("iznos pdv a", "iznos") == 0
    assert phrase_score("oib narucitelja", "oib") == 0


def test_multi_word_phrase_contained_in_a_long_header_still_matches() -> None:
    long_header = normalise_header(
        "Naziv ponuditelja s kojim je sklopljen ugovor /OS i naziv podizvoditelja ako postoje"
    )
    assert 80 <= phrase_score(long_header, "naziv ponuditelja") < 100


def test_real_headers_dugo_selo_csv() -> None:
    table = read_table(CSV, "csv")
    idx, mapping = find_header(table)
    assert idx == 6
    assert set(mapping) == {"predmet", "amount", "date", "bidder"}
    assert mapped_groups(mapping) == 4
    header = table[idx]
    assert header[mapping["predmet"]] == "Predmet ugovora"
    assert "s PDV-om" in header[mapping["amount"]]
    assert header[mapping["bidder"]].startswith("Naziv ponuditelja")


def test_real_headers_kravarsko_xlsx_do_not_pick_buyer_or_vat_columns() -> None:
    table = read_table(XLSX, "xlsx")
    idx, mapping = find_header(table)
    header = [str(h) for h in table[idx]]
    assert (
        header[mapping["bidder_oib"]] == "OIB ugovaratelja"
    )  # not "OIB Naručitelja", not the subcontractor
    assert header[mapping["bidder"]] == "Naziv ugovaratelja"
    assert header[mapping["date"]] == "Datum sklapanja"  # not "Datum izvršenja"
    assert header[mapping["amount"]] == "Iznos bez PDV-a"  # not "Iznos PDV-a"
    assert header[mapping["cpv"]] == "CPV"
    assert header[mapping["predmet"]] == "Predmet nabave"
    assert mapped_groups(mapping) == 5


def test_real_rows_csv() -> None:
    table = read_table(CSV, "csv")
    idx, mapping = find_header(table)
    rows = extract_rows(table, idx, mapping)
    assert len(rows) == 14
    first = rows[0]
    assert first["bidder"] == "FUTURA AUTO d.o.o."  # first line of the cell only (address dropped)
    assert first["bidder_oib"] == "42754118124"  # OIB read from the cell text
    assert first["amount"] == Decimal("45258.47")
    assert "\n" in first["predmet"]


def test_real_rows_xlsx() -> None:
    table = read_table(XLSX, "xlsx")
    idx, mapping = find_header(table)
    rows = extract_rows(table, idx, mapping)
    assert len(rows) == 37
    first = rows[0]
    assert first["cpv"] == "45310000"
    assert first["bidder_oib"] == "91001684089"  # the contractor, not the buyer (47763874566)
    assert first["contract_date"] == date(2024, 3, 27)  # "Datum sklapanja", not "Datum izvršenja"
    assert first["amount"] == Decimal("26394.5")  # net amount, not the VAT column (6598.63)


def test_files_with_fewer_than_three_fields_are_not_kept() -> None:
    mapping = map_headers(["Red.br.", "Datum sklapanja", "Ugovorna stranka", "Predmet ugovora", ""])
    assert mapped_groups(mapping) == 3  # date, bidder, predmet -> kept
    assert mapped_groups(map_headers(["Datum sklapanja", "Predmet ugovora"])) == 2  # rejected
    assert mapped_groups(map_headers(["a", "b", "c"])) == 0


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("6.000,00", Decimal("6000.00")),
        ("1234.56", Decimal("1234.56")),
        ("1 234,56 EUR", Decimal("1234.56")),
        ("1,234.56", Decimal("1234.56")),
        (1500, Decimal("1500")),
        ("1.234.567", Decimal("1234567")),
        ("", None),
        ("n/a", None),
        (None, None),
    ],
)
def test_parse_amount(raw: object, expected: Decimal | None) -> None:
    assert parse_amount(raw) == expected


def test_parse_date_and_cpv() -> None:
    assert parse_date("14.01.2022.") == date(2022, 1, 14)
    assert parse_date("2024-12-31") == date(2024, 12, 31)
    assert parse_date("31.02.2022") is None
    assert parse_date("nema") is None
    assert clean_cpv("45310000-3") == "45310000"
    assert clean_cpv("45") == "45"
    assert clean_cpv("tekst") is None


def test_company_name_detection_protects_natural_persons() -> None:
    assert is_company_name("FUTURA AUTO d.o.o.")
    assert is_company_name("ENTERCOM d.o.o.")
    assert is_company_name("Komunalac j.d.o.o.")
    assert not is_company_name("Ivan Horvat")
    assert not is_company_name("Marija Kovač obrt za usluge")
