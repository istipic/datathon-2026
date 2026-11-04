"""Registration of NabavaRadar's data sources (``data_source`` rows)."""

from __future__ import annotations

from sqlalchemy.orm import Session

from nabavaradar_api.constants import (
    SRC_CPV,
    SRC_DERIVED,
    SRC_MUNICIPAL,
    SRC_SUDREG,
    SRC_TED_COMPETITION,
    SRC_TED_RESULT,
)
from nabavaradar_api.settings import NabavaSettings
from opendata_core.provenance import AccessMethod, Tier, register_source

LICENCE_NOTE = "The publisher's licence was not stated in the retrieved documents; check before reuse."


def register_all(session: Session, settings: NabavaSettings) -> None:
    """Idempotently register every source used by the app."""
    env = "TEST environment (sudreg-data-test.gov.hr)" if settings.sudreg_is_test else "production"
    register_source(
        session,
        id=SRC_SUDREG,
        title="Sudski registar - otvoreni podaci (javni servis, v3)",
        publisher="Ministarstvo pravosuđa, uprave i digitalne transformacije RH",
        url="https://sudreg-data.gov.hr/",
        access_method=AccessMethod.api,
        tier=Tier.official,
        notes=(
            f"Environment used: {env}. Company-level fields only (OIB, MBS, name, status, county, "
            "NKD codes); sole traders, bankruptcy/liquidation subjects and natural persons are "
            f"never stored. Data is as old as the snapshot shown in the ingestion run. {LICENCE_NOTE}"
        ),
    )
    register_source(
        session,
        id=SRC_TED_COMPETITION,
        title="TED - obavijesti o nadmetanju (naručitelji iz Hrvatske)",
        publisher="Ured za publikacije Europske unije (TED)",
        url="https://ted.europa.eu/",
        access_method=AccessMethod.api,
        tier=Tier.eu_official,
        notes=f"POST {settings.ted_search_url}, buyer-country=HRV, cn-standard/cn-social/cn-desg. {LICENCE_NOTE}",
    )
    register_source(
        session,
        id=SRC_TED_RESULT,
        title="TED - obavijesti o dodjeli ugovora (naručitelji iz Hrvatske)",
        publisher="Ured za publikacije Europske unije (TED)",
        url="https://ted.europa.eu/",
        access_method=AccessMethod.api,
        tier=Tier.eu_official,
        notes=(
            "can-standard/can-social/can-desg. Notices before about 2024-02 are legacy TED notices "
            f"without winner and submissions data in the API. {LICENCE_NOTE}"
        ),
    )
    register_source(
        session,
        id=SRC_CPV,
        title="CPV 2008 - Common Procurement Vocabulary (24 jezika)",
        publisher="Ured za publikacije Europske unije",
        url="https://ted.europa.eu/documents/d/ted/cpv_2008_xls",
        access_method=AccessMethod.download,
        tier=Tier.eu_official,
        notes=f"Official workbook cpv_2008_ver_2013.xlsx with Croatian labels. {LICENCE_NOTE}",
    )
    register_source(
        session,
        id=SRC_MUNICIPAL,
        title="Registri ugovora javne nabave (gradovi i općine, CKAN)",
        publisher="Portal otvorenih podataka RH (data.gov.hr)",
        url="https://data.gov.hr/",
        access_method=AccessMethod.api,
        tier=Tier.community,
        notes="P1. Columns are mapped by fuzzy header matching; only files with >= 3 mapped fields are kept.",
    )
    register_source(
        session,
        id=SRC_DERIVED,
        title="NabavaRadar - izvedeni podaci (NKD-CPV povezivanje, statistika konkurencije)",
        publisher="NabavaRadar",
        url="https://github.com/",
        access_method=AccessMethod.derived,
        tier=Tier.derived,
        notes="Computed from the sources above with multilingual-e5-small embeddings.",
    )
    session.commit()
