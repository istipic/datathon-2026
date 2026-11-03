"""Shared constants: categories, personas, source ids, geography."""

from __future__ import annotations

CATEGORIES = (
    "lijecnik",
    "ljekarna",
    "vrtic",
    "skola",
    "knjiznica",
    "posta",
    "prijevoz",
    "park",
    "namirnice",
)
PERSONAS = ("opce", "starija", "roditelj", "kolica")
VARIANTS = ("full", "wheelchair")

# Source ids (data_source.id)
SRC_VRTICI = "zg-vrtici"
SRC_VRTICI_MJESTA = "zg-vrtici-mjesta"
SRC_SKOLE = "zg-skole"
SRC_GTFS = "zet-gtfs"
SRC_OSM = "osm-zagreb"
SRC_GRID = "eurostat-census-grid-2021"
SRC_GRAPH = "blizu-derived-graph"

PLACE = "Grad Zagreb, Croatia"
# Nominatim viewbox (min_lon, min_lat, max_lon, max_lat) = 15.75,45.95,16.25,45.70 as lon,lat pairs
ZAGREB_VIEWBOX = (15.75, 45.70, 16.25, 45.95)

CRS_WGS84 = 4326
CRS_METRIC = 3765  # HTRS96/TM
CRS_GRID = 3035  # ETRS89-LAEA (Eurostat grid)

SNAP_MAX_M = 200.0  # facility -> network node
ADDRESS_SNAP_MAX_M = 300.0  # user address -> network node
DIJKSTRA_LIMIT_M = 4000.0
