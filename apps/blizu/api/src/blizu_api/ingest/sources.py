"""Registration of Blizu's data sources (``data_source`` rows).

Titles, publishers and licences of the CKAN datasets are read from the live CKAN metadata, not
typed in. Licence information the publisher did not provide stays empty and is flagged in the notes.
"""

from __future__ import annotations

from sqlalchemy.orm import Session

from blizu_api.constants import (
    SRC_GRAPH,
    SRC_GTFS,
    SRC_OSM,
    SRC_SKOLE,
    SRC_VRTICI,
    SRC_VRTICI_MJESTA,
)
from opendata_core.ckan import CkanClient
from opendata_core.provenance import AccessMethod, Tier, register_source

CKAN_PACKAGES = {
    SRC_VRTICI: "geoportal-djecji-vrtici",
    SRC_VRTICI_MJESTA: "slobodna-mjesta-u-vrticima-i-obrtima-za-cuvanje-djece-grada-zagreba",
    SRC_SKOLE: "djeji-vrtii-osnovne-i-srednje-kole-grada-zagreba-inspire",
}
CKAN_DATASET_URL = "https://data.gov.hr/ckan/dataset/"
GTFS_URL = "https://zet.hr/gtfs-scheduled/latest"
OSM_COPYRIGHT_URL = "https://www.openstreetmap.org/copyright"
ODBL_URL = "https://opendatacommons.org/licenses/odbl/1-0/"


def register_ckan_sources(session: Session, ckan: CkanClient) -> None:
    """Register zg-vrtici, zg-vrtici-mjesta and zg-skole from their CKAN package metadata."""
    notes = {
        SRC_VRTICI: "CSV iz ArcGIS izvoza (EPSG:4326). Uključeni su gradski, privatni i vjerski vrtići; "
        "izuzeti su 'Vrtić u bolnici' i 'Posebna ustanova'.",
        SRC_VRTICI_MJESTA: "Stanje 01.01.2025. (gradski dječji vrtići), spajanje po nazivu ustanove, ne po lokaciji.",
        SRC_SKOLE: "INSPIRE WFS (us-govserv:GovernmentalService), samo osnovno obrazovanje. "
        "Izvor ne sadrži nazive ni adrese; nazivi se, gdje postoji OSM objekt unutar 50 m, "
        "preuzimaju iz OpenStreetMapa (ODbL). Licencija nije navedena u metapodacima CKAN-a.",
    }
    for source_id, package in CKAN_PACKAGES.items():
        pkg = ckan.package_show(package)
        org = (pkg.get("organization") or {}).get("title") or "nepoznat izdavač"
        register_source(
            session,
            id=source_id,
            title=pkg["title"],
            publisher=org,
            url=f"{CKAN_DATASET_URL}{pkg['name']}",
            license_name=pkg.get("license_title"),
            license_url=pkg.get("license_url"),
            access_method=AccessMethod.api if source_id == SRC_SKOLE else AccessMethod.download,
            tier=Tier.official,
            notes=notes[source_id],
        )


def register_static_sources(session: Session) -> None:
    """Register sources that are not on CKAN: ZET GTFS, OSM and the derived graph."""
    register_source(
        session,
        id=SRC_GTFS,
        title="ZET GTFS (statični vozni red)",
        publisher="Zagrebački električni tramvaj (ZET)",
        url=GTFS_URL,
        license_name=None,
        license_url=None,
        access_method=AccessMethod.download,
        tier=Tier.official,
        notes="Licencija nije navedena uz feed. Učestalost polazaka računa se za jutarnji vrh "
        "(07:00–09:00) referentne srijede.",
    )
    register_graph_sources(session)


def register_graph_sources(session: Session) -> None:
    """Register osm-zagreb (community) and blizu-derived-graph (derived)."""
    register_source(
        session,
        id=SRC_OSM,
        title="OpenStreetMap: pješačka mreža i objekti, Grad Zagreb",
        publisher="OpenStreetMap contributors",
        url=OSM_COPYRIGHT_URL,
        license_name="ODbL 1.0",
        license_url=ODBL_URL,
        access_method=AccessMethod.api,
        tier=Tier.community,
        notes="Overpass API preko osmnx. Potpunost podataka ovisi o volonterima; atribucija: "
        "© OpenStreetMap contributors.",
    )
    register_source(
        session,
        id=SRC_GRAPH,
        title="Blizu: izvedeni pješački graf (puni i za invalidska kolica)",
        publisher="Blizu (izvedeno iz OpenStreetMapa)",
        url=OSM_COPYRIGHT_URL,
        license_name="ODbL 1.0 (izvedena baza)",
        license_url=ODBL_URL,
        access_method=AccessMethod.derived,
        tier=Tier.derived,
        notes="Neusmjereni graf, težina brida = duljina u metrima; graf za kolica isključuje "
        "highway=steps i wheelchair=no.",
    )
