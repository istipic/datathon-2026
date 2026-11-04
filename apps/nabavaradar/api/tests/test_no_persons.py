"""No natural-person data in the database (acceptance criterion).

- the ORM models and the migrated schema have no person-name columns in the company tables;
- the parsers read named keys only, so personal fields of a register response cannot leak through;
- with ``TEST_REAL_DATABASE_URL`` set, the loaded company tables are scanned for sole-trader forms.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path

import psycopg
import pytest
from sqlalchemy.engine import make_url

from nabavaradar_api import db  # noqa: F401  (registers the models)
from nabavaradar_api.sudreg.parse import parse_detail
from opendata_core.db import Base

COMPANY_TABLES = ("company", "company_activity", "nkd", "cpv", "crosswalk", "competition_stat")
PERSON_COLUMN = re.compile(
    r"(prezime|first_?name|last_?name|surname|given_?name|full_?name|person|osoba|osobe|funkcij|zastupnik|"
    r"clan|member|director|direktor|birth|rodjen|datum_rodjenja|jmbg|passport|osobna)",
    re.IGNORECASE,
)
FIX = (
    Path(__file__).parent
    / "fixtures"
    / "sudreg"
    / "2026-11-04_detalji_subjekta_oib92803032010.json"
)


def test_company_tables_have_no_person_columns_in_the_models() -> None:
    for name in COMPANY_TABLES:
        for column in Base.metadata.tables[name].columns:
            assert not PERSON_COLUMN.search(column.name), f"{name}.{column.name}"


@pytest.mark.db
def test_company_tables_have_no_person_columns_in_the_migrated_schema(test_db_url: str) -> None:
    server = (
        make_url(test_db_url).set(drivername="postgresql").render_as_string(hide_password=False)
    )
    with psycopg.connect(server) as conn:
        rows = conn.execute(
            "select table_name, column_name from information_schema.columns "
            "where table_schema = 'public' and table_name = any(%s)",
            (list(COMPANY_TABLES),),
        ).fetchall()
    assert rows
    offenders = [(t, c) for t, c in rows if PERSON_COLUMN.search(c)]
    assert offenders == []


def test_parser_output_carries_company_level_fields_only() -> None:
    body = json.loads(FIX.read_text(encoding="utf-8"))["body"]
    # simulate a response that does contain person data (e.g. from a state-body service)
    body["osobe"] = [{"osoba_rbr": 1, "ime": "Ime", "prezime": "Prezime", "oib": 12345678903}]
    body["funkcije_osoba"] = [{"funkcija": "direktor"}]
    record = parse_detail(body)
    assert record is not None
    assert "Prezime" not in json.dumps(vars(record), default=str)
    assert set(vars(record)) == {
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


@pytest.mark.skipif(
    not os.environ.get("TEST_REAL_DATABASE_URL"),
    reason="set TEST_REAL_DATABASE_URL to scan loaded data",
)
def test_loaded_company_rows_contain_no_sole_traders_or_estates() -> None:
    # "obrt" inside a legal entity's name (a school, a museum, 'd.o.o. za obrt, trgovinu...') is fine;
    # sole-trader markers are 'trgovac pojedinac', 't.p.', a leading 'Obrt'/'vl.' or 'vlasnik'.
    server = (
        make_url(os.environ["TEST_REAL_DATABASE_URL"])
        .set(drivername="postgresql")
        .render_as_string(hide_password=False)
    )
    with psycopg.connect(server) as conn:
        n = conn.execute("select count(*) from company").fetchone()[0]  # type: ignore[index]
        bad = conn.execute(
            "select count(*) from company where name ~* '(trgovac pojedinac|\\mt\\.p\\.\\M|^obrt\\M|^vl\\.|\\mvlasnik\\M|stečajna masa|likvidacijska masa)'"
        ).fetchone()[0]  # type: ignore[index]
    assert n > 0
    assert bad == 0
