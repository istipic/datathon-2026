"""Deterministic advice rules for public buyers, each tied to a source.

Legal citations quote the original text of the Zakon o javnoj nabavi (NN 120/2016) that was opened
and read on 2026-11-04 (verbatim extracts: data/evidence/2026-11-04_zjn_nn120-2016_clanci_198_204_228.json).
The law has been amended since (e.g. NN 114/22): the buyer must check the current consolidated text.
"""

from __future__ import annotations

from typing import Any

from nabavaradar_api.constants import SINGLE_BID_FLAG_MIN_N, SINGLE_BID_FLAG_SHARE

ZJN_URL = "https://narodne-novine.nn.hr/clanci/sluzbeni/2016_12_120_2607.html"
SUDREG_URL = "https://sudreg-data.gov.hr/"
TED_URL = "https://ted.europa.eu/"
FEW_SUPPLIERS = (
    5  # task: fewer than 5 capable suppliers in the county -> suggest NUTS2-wide publication
)


def build_advice(
    *,
    single_bid_share: float | None,
    n_awards: int | None,
    competition_scope: str | None,
    suppliers_in_county: int | None,
    county_name: str | None,
    suppliers_in_region: int | None,
    region_code: str | None,
) -> list[dict[str, Any]]:
    """Advice items ``{rule, text, source_url, source_label}`` for the given market facts."""
    out: list[dict[str, Any]] = []
    low_competition = (
        single_bid_share is not None
        and n_awards is not None
        and n_awards >= SINGLE_BID_FLAG_MIN_N
        and single_bid_share >= SINGLE_BID_FLAG_SHARE
    )
    if low_competition:
        share = f"{single_bid_share * 100:.0f} %"
        evidence = (
            f"U sličnim nabavama ({competition_scope}) {share} dodjela imalo je samo jednu ponudu "
            f"(n = {n_awards})."
        )
        out.append(
            {
                "rule": "single_bid_lots",
                "text": (
                    f"{evidence} Razmotrite podjelu predmeta nabave na grupe kako bi se povećao pristup "
                    "malih i srednjih gospodarskih subjekata. Ako nabavu ne dijelite na grupe, u "
                    "dokumentaciji o nabavi treba navesti glavne razloge."
                ),
                "source_url": ZJN_URL,
                "source_label": "Zakon o javnoj nabavi (NN 120/16), čl. 204. st. 1. i 2.",
            }
        )
        out.append(
            {
                "rule": "single_bid_deadline",
                "text": (
                    f"{evidence} Razmotrite rok za dostavu ponuda dulji od zakonskog minimuma "
                    "(u otvorenom postupku velike vrijednosti minimalni rok je 35 dana od dana "
                    "slanja poziva na nadmetanje)."
                ),
                "source_url": ZJN_URL,
                "source_label": "Zakon o javnoj nabavi (NN 120/16), čl. 228.",
            }
        )
        out.append(
            {
                "rule": "single_bid_consultation",
                "text": (
                    f"{evidence} Provedite analizu tržišta i prethodno savjetovanje sa zainteresiranim "
                    "gospodarskim subjektima. Za radove u otvorenom ili ograničenom postupku te za "
                    "robu ili usluge velike vrijednosti savjetovanje je obvezno i traje najmanje pet "
                    "dana, a naručitelj mora razmotriti primjedbe i objaviti izvješće."
                ),
                "source_url": ZJN_URL,
                "source_label": "Zakon o javnoj nabavi (NN 120/16), čl. 198. st. 1., 3. i 4.",
            }
        )
    if suppliers_in_county is not None and suppliers_in_county < FEW_SUPPLIERS:
        region = (
            f" (regija {region_code}: {suppliers_in_region} dobavljača)"
            if suppliers_in_region is not None
            else ""
        )
        out.append(
            {
                "rule": "few_suppliers_county",
                "text": (
                    f"U županiji {county_name} djeluje manje od {FEW_SUPPLIERS} dobavljača s relevantnim "
                    f"djelatnostima (broj: {suppliers_in_county}){region}. Razmotrite objavu nabave na "
                    "razini cijele NUTS2 regije, a ne samo županije, kako biste osigurali dovoljno ponuda."
                ),
                "source_url": SUDREG_URL,
                "source_label": "Sudski registar (aktivni subjekti s NKD djelatnostima); izračun Birokratko",
            }
        )
    return out
