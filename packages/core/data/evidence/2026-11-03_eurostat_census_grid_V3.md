# Eurostat Census 2021 population grid — probe evidence (retrieved 2026-11-03)

- Landing page: https://ec.europa.eu/eurostat/web/gisco/geodata/population-distribution/population-grids
- Download used: https://gisco-services.ec.europa.eu/census/2021/Eurostat_Census-GRID_2021_V3.zip
  - size 566125577 bytes, Last-Modified Fri, 19 Jun 2026 11:29:37 GMT (see *_zip_headers.txt)
  - sha256 of the file downloaded on 2026-11-03:
    18a467e3d96b71dd89f0440cc184751bded45721cdff8ba778ece79d7a4f5843
- Members: ESTAT_Census_2021_V3.csv / .gpkg / .parquet / .tiff, ESTAT_Census_2021_country.csv.zip, read.me
  (copy of read.me: *_read.me.txt)
- CRS: ETRS89-LAEA (EPSG:3035). GPKG layer `ESTAT_Census_2021_V3` (Polygon), 4 595 932 features.
- CSV/GPKG fields: GRD_ID, T, M, F, Y_LT15, Y_1564, Y_GE65, EMP, NAT, EU_OTH, OTH, SAME, CHG_IN,
  CHG_OUT, LAND_SURFACE, POPULATED, CNTR_ID
- Not-available codes: -8888 (confidentiality), -9999 (other reasons).
- Licence/terms: "Copyright European Union 2026 — the source needs to be indicated and, when re-use involves
  modifications, this must be stated" (https://ec.europa.eu/eurostat/web/main/about-us/policies/copyright).
- Croatia: cells whose CNTR_ID (dash-separated list) contains HR → 60 873 cells
  (HR: 59809, HR-SI: 662, HR-HU: 400, HR-HU-SI: 2); sum(T) = 3 889 177 (includes neighbours'
  population in the 1 064 shared border cells); age fields present with no -8888/-9999 values in HR.
  Full output: *_probe_output.txt
- GRD_ID format `CRS3035RES<res>mN<northing>E<easting>` = SOUTH-WEST corner of the cell in EPSG:3035.
  Verified: CRS3035RES1000mN2490000E4595000 has GPKG polygon bounds (4595000, 2490000, 4596000, 2491000).
- Per-country INSPIRE package https://gisco-services.ec.europa.eu/census/2021/INSPIRE/Data/HR_PD_3035_GPKG.zip
  is listed (3.3M) but returned HTTP 503 "Backend fetch failed" on 8 attempts on 2026-11-03
  (also HR_PD_3035_CSV.zip, HR_PD_3035_GML.zip) — hence the EU-wide V3 package is the source.
