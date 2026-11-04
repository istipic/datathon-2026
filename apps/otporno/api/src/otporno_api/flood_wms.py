"""WMS capabilities of Hrvatske vode: which hazard layers exist and whether they are queryable.

This is the check behind the flood decision ladder (docs/adr/0007): a hazard layer that is not
``queryable`` cannot answer GetFeatureInfo, so without WFS or a vector download the flood level of a point
cannot be read from the service (ladder step c: show the WMS as an overlay only).
"""

from __future__ import annotations

import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx

from opendata_core import http as http_mod
from otporno_api.constants import HV_LAYERS
from otporno_api.settings import OtpornoSettings

NS = {"w": "http://www.opengis.net/wms"}


@dataclass(frozen=True)
class WmsLayer:
    """One named layer of a capabilities document."""

    name: str
    title: str
    queryable: bool
    bbox: tuple[float, float, float, float] | None  # (west, south, east, north) in WGS84


def parse_capabilities(xml: str | bytes) -> list[WmsLayer]:
    """All named layers of a WMS 1.3.0 capabilities document."""
    root = ET.fromstring(xml)  # noqa: S314 (fixed public HV capabilities document, not user input)
    layers: list[WmsLayer] = []
    for el in root.iter("{http://www.opengis.net/wms}Layer"):
        name = el.findtext("w:Name", namespaces=NS)
        if not name:
            continue
        box = el.find("w:EX_GeographicBoundingBox", NS)
        bbox = None
        if box is not None:
            try:
                bbox = (
                    float(box.findtext("w:westBoundLongitude", namespaces=NS) or "nan"),
                    float(box.findtext("w:southBoundLatitude", namespaces=NS) or "nan"),
                    float(box.findtext("w:eastBoundLongitude", namespaces=NS) or "nan"),
                    float(box.findtext("w:northBoundLatitude", namespaces=NS) or "nan"),
                )
            except ValueError:
                bbox = None
        layers.append(
            WmsLayer(
                name, el.findtext("w:Title", namespaces=NS) or "", el.get("queryable") == "1", bbox
            )
        )
    return layers


def hazard_layers(layers: list[WmsLayer]) -> dict[str, WmsLayer | None]:
    """The three 2019 hazard layers (high/medium/low probability) among the parsed layers."""
    by_name = {layer.name: layer for layer in layers}
    return {scenario: by_name.get(name) for scenario, name in HV_LAYERS.items()}


def ladder_step(layers: list[WmsLayer]) -> str:
    """``b`` when all three hazard layers are queryable, otherwise ``c`` (WFS and vectors are handled elsewhere)."""
    found = hazard_layers(layers)
    if all(layer is not None and layer.queryable for layer in found.values()):
        return "b"
    return "c"


def fetch_capabilities(settings: OtpornoSettings, client: httpx.Client | None = None) -> str:
    """``GetCapabilities`` of the Hrvatske vode WMS (the document the layer names come from)."""
    own = client is None
    client = client or http_mod.make_client(settings)
    try:
        response = client.get(
            settings.hv_wms_url,
            params={"SERVICE": "WMS", "VERSION": "1.3.0", "REQUEST": "GetCapabilities"},
        )
        response.raise_for_status()
        return response.text
    finally:
        if own:
            client.close()
