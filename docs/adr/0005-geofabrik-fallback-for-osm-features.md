# ADR 0005: Geofabrik extract (via `osmium`) as fallback for OSM features

- Status: accepted
- Date: 2026-11-03

## Context

Blizu needs six OpenStreetMap feature categories (doctors/clinics, pharmacies, libraries, post offices, parks,
supermarkets/convenience shops) plus school names, and the walking network of Grad Zagreb. The task specifies
`osmnx` (Overpass API). During development the public Overpass servers were unusable for long periods:
`502 Bad Gateway … at capacity`, `ConnectTimeout`, and `403` on the OSM-France instance (whitelist only).
One `graph_from_place` call took 77 minutes (two alternate endpoints each burned a 600 s read timeout) and
the feature queries repeatedly failed. A data pipeline that must "complete from scratch in < 30 min" cannot
depend on that.

## Decision

- Keep `osmnx`/Overpass as the primary source. Add **`OSM_FEATURE_SOURCE=auto|overpass|geofabrik`**
  (default `auto`): try Overpass with 2 quick attempts (90 s timeout) and then fall back to the Geofabrik
  extract `croatia-latest.osm.pbf` (≈ 200 MB, daily), read with **`osmium`** (pyosmium 4.x,
  `FileProcessor` with a key filter; the whole of Croatia is scanned in ≈ 10 s).
- The extract is clipped to the Grad Zagreb boundary, geometry conversion matches `osmnx.features_from_place`
  (nodes and assembled areas; the same `osm_features_to_frame` code), and provenance records which route was used
  (`ingestion_run.retrieved_url`, `source_last_modified` = Geofabrik snapshot time, `manifest.json: osm_via`).
- The **graph** step has the same two routes (`blizu_api/ingest/graph_pbf.py`): the osmnx "walk" filter is
  reproduced exactly (including its regex semantics), ways are split into one edge per node pair, nodes outside
  the Grad Zagreb polygon are dropped and only the largest connected component is kept. Measured against the
  osmnx graph on 40 random node pairs: median network-distance ratio 1.000 (p10 0.965, p90 1.01). The graph is
  larger (344 k nodes vs 83 k: no intersection simplification) but `/access` stays at p95 < 5 ms and the cold
  optimiser at ≈ 3.5 s. `auto` gives Overpass one attempt (3 min) for the graph before using the extract.
  A from-scratch `blizu ingest all` with Overpass down took 466 s.
- Overpass endpoints that do not work for automated use were removed from the rotation
  (`overpass.openstreetmap.fr` answers 403, `overpass.kumi.systems` and `overpass.private.coffee` time out).

## Why `osmium`

It is the standard reader for OSM PBF with area assembly, ships wheels for Windows and Linux, and is the only
new runtime dependency (`osmium>=4`). Alternatives (`pyrosm`, GDAL OSM driver) are heavier or lack multipolygon
assembly of the quality needed for parks.

## Consequences

- OSM data from the extract is up to a day old; the data age is shown (`freshness_days`) like for any source.
- Both routes produce the same schema; tests for both the conversion (`osm_features_to_frame`) and the
  Geofabrik route (real extract, 2026-11-03) exist.
- The Docker image grows by the `osmium` wheel (a few MB).
