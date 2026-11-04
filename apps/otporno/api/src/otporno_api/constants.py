"""Source ids and shared constants."""

from __future__ import annotations

SRC_HV_FLOOD = "hv-flood-2019"
SRC_OPEN_METEO = "open-meteo-climate"
SRC_POPGRID = "eurostat-census-grid-2021"  # registered by opendata_core.popgrid
SRC_LAU = "gisco-lau"
SRC_OSM_BUILDINGS = "osm-public-buildings"
SRC_DHMZ = "dhmz-observations"
SRC_CORINE = "corine-2018"
SRC_DERIVED = "otporno-derived"

# Open-Meteo Climate API (docs 2026-11-04: https://open-meteo.com/en/docs/climate-api)
MODELS = ("CMCC_CM2_VHR4", "EC_Earth3P_HR", "MRI_AGCM3_2_S")
BASE_YEARS = (1991, 2020)  # "today" = 1991-2020 climatology
FUT_YEARS = (2031, 2050)
HOT_DAY_C = 30.0  # Tmax >= 30 C
TROPICAL_NIGHT_C = 20.0  # Tmin >= 20 C

# Hrvatske vode, Karte opasnosti od poplava 2019 (return periods as stated by HV)
HV_LAYERS = {
    "high": "poplave_opasnosti_2019:hr.fd.opasnost-od-poplave-velika-vjerojatnost_2019",
    "medium": "poplave_opasnosti_2019:hr.fd.opasnost-od-poplave-srednja-vjerojatnost_2019",
    "low": "poplave_opasnosti_2019:hr.fd.opasnost-od-poplave-mala-vjerojatnost_2019",
}
FLOOD_MAP_YEAR = 2019
FLOOD_DISCLAIMER = (
    "Karte opasnosti od poplava su informativne; Hrvatske vode ne jamče za posljedice korištenja. "
    "Izvor: Hrvatske vode, 2019."
)
FLOOD_UNAVAILABLE = "Automatska procjena nije dostupna; pogledajte kartu."

# Bands: niska < 0.25 <= umjerena < 0.5 <= visoka < 0.8 <= vrlo visoka
BAND_EDGES = (0.25, 0.5, 0.8)
BANDS = ("niska", "umjerena", "visoka", "vrlo visoka")

# Priority weights (fire weight 0 and renormalised until fire exists)
DEFAULT_WEIGHTS = {"flood": 0.5, "heat": 0.35, "fire": 0.15}
CHILD_WORKING_AGE_FACTOR = 0.5  # non-65+ residents count half

# Cooling centres: 10 min at 0.9 m/s with a detour factor of 1.3 -> 540 m / 1.3 = 415 m straight line
COOLING_RADIUS_M = 415.0
LATTICE_M = 250.0
