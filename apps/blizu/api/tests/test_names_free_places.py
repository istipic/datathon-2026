"""Name normalisation, fuzzy join and the free-places parser on the REAL 2026-11-03 files."""

from __future__ import annotations

import csv
import io
import json
from datetime import date
from pathlib import Path

import pandas as pd
import pytest

from blizu_api.ingest.facilities import parse_vrtici
from blizu_api.ingest.free_places import parse_free_places
from blizu_api.names import MATCH_THRESHOLD, fuzzy_join, normalise_name
from opendata_core.ckan import newest_resource

FIX = Path(__file__).parent / "fixtures"
FREE = FIX / "zg-vrtici-mjesta" / "2026-11-03_slobodna_mjesta_dv_2025-01-01.csv"
REGISTER = FIX / "zg-vrtici" / "2026-11-03_vrtici_full.csv"


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("DV Bajka", "bajka"),
        ("BAJKA", "bajka"),
        ("Dječji vrtić Maslačak", "maslacak"),
        ("DV Šegrt Hlapić", "segrt hlapic"),
        ("ŠEGRT HLAPIĆ", "segrt hlapic"),
        ("DV Đurđica", "durdica"),
        ("  DV   Ivane Brlić-Mažuranić ", "ivane brlic mazuranic"),
        ("Gradski dječji vrtić Pčelica", "pcelica"),
        ("", ""),
    ],
)
def test_normalise_name(raw: str, expected: str) -> None:
    assert normalise_name(raw) == expected


def test_fuzzy_join_respects_the_threshold() -> None:
    register = ["MALI PRINC", "EN TEN TINI", "SUNCE"]
    out = fuzzy_join(["DV Mali Princ", "DV Ententini", "DV Nepostojeći vrtić"], register)
    assert [m.right_index for m in out] == [0, 1, None]
    assert out[0].score == 100
    assert out[1].score == pytest.approx(
        90.0
    )  # 'ententini' vs 'en ten tini': exactly at the cut-off
    assert out[2].score == 0.0
    assert MATCH_THRESHOLD == 90.0
    # a stricter threshold drops the fuzzy match, never forces a wrong one
    assert fuzzy_join(["DV Ententini"], register, threshold=95)[0].right_index is None


def test_free_places_parse_real_file() -> None:
    rows, snapshot = parse_free_places(FREE.read_text(encoding="utf-8"))
    assert snapshot == date(2025, 1, 1)  # from the "STANJE NA DAN 1.1.2025." line
    assert len(rows) == 60
    assert all(r.name.startswith("DV ") for r in rows)
    assert "UKUPNO" not in {r.name.upper() for r in rows}
    # cross-check the sums with the file's own "UKUPNO" row (independent csv reading)
    table = list(csv.reader(io.StringIO(FREE.read_text(encoding="utf-8-sig")), delimiter=";"))
    totals = next(r for r in table if r[0].strip().upper() == "UKUPNO")
    assert sum(r.vrtic_free for r in rows) == int(totals[22])
    assert sum(r.jaslice_free for r in rows) == int(totals[11])
    first = rows[0]
    assert (first.district, first.name, first.vrtic_free) == ("DONJI GRAD", "DV Budućnost", 4)
    assert first.total_free == first.jaslice_free + first.vrtic_free
    assert first.attrs["VRTIĆ|UKUPNO|UKUPNO RED. + POS."] == 4


def test_free_places_parse_rejects_garbage() -> None:
    with pytest.raises(ValueError, match="no data rows"):
        parse_free_places("a;b\n")
    with pytest.raises(ValueError, match="JASLICE"):
        parse_free_places("x;y;z\n;;\n;;\nA;B;C\n")


def test_every_free_places_name_joins_the_register() -> None:
    rows, _ = parse_free_places(FREE.read_text(encoding="utf-8"))
    register = parse_vrtici(REGISTER.read_text(encoding="utf-8"))
    names = sorted({str(n) for n in register["name"].dropna()})
    assert len(names) > 100
    matches = fuzzy_join([r.name for r in rows], names)
    assert all(m.right_index is not None for m in matches)  # 60 / 60 on the real data
    by_name = {
        rows[m.left_index].name: names[m.right_index] for m in matches if m.right_index is not None
    }
    assert by_name["DV Ententini"] == "EN TEN TINI"
    assert by_name["DV Šegrt Hlapić"] == "ŠEGRT HLAPIĆ"
    # one-to-one: no two free-places rows collapse onto the same register entry
    assert len(set(by_name.values())) == len(by_name)


def test_register_has_kindergartens_without_free_places() -> None:
    """Private/religious kindergartens are in the register but not in the city table."""
    rows, _ = parse_free_places(FREE.read_text(encoding="utf-8"))
    register = parse_vrtici(REGISTER.read_text(encoding="utf-8"))
    names = sorted({str(n) for n in register["name"].dropna()})
    matched = {m.right_index for m in fuzzy_join([r.name for r in rows], names)}
    assert len(names) - len(matched) > 50


def test_ckan_newest_csv_is_the_city_kindergarten_table() -> None:
    """The package has two CSVs (nannies and city kindergartens): newest_resource picks the latter."""
    pkg = json.loads(
        (FIX / "zg-vrtici-mjesta" / "2026-11-03_package_show.json").read_text(encoding="utf-8")
    )
    resource = newest_resource(pkg["result"], ["CSV"])
    assert resource is not None
    assert resource["id"] == "a6a9199d-eaf4-4f75-9bce-7a3a5b367d30"
    assert "gradskim DV" in resource["name"]
    other = [
        r for r in pkg["result"]["resources"] if r["format"] == "CSV" and r["id"] != resource["id"]
    ]
    assert other
    assert "dadilje" in other[0]["name"]


def test_register_fixture_matches_the_sample_columns() -> None:
    df = pd.read_csv(REGISTER, encoding="utf-8-sig")
    assert {"X", "Y", "OBJECTID", "naziv", "adresa", "vr_vrtica"} <= set(df.columns)
    assert df["X"].between(15.5, 16.5).all()
