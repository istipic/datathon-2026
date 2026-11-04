# ADR 0007: Otporko data decisions (flood ladder, Open-Meteo quota, cooling candidates)

- Status: accepted
- Date: 2026-11-04

## Context

Otporko combines three public sources whose access turned out to be narrower than the task assumed.
Evidence for every statement below is saved in `apps/otporno/data/evidence/` (all dated 2026-11-04).

## Decision 1: flood runs on ladder step c (WMS overlay only)

The task prescribes a decision ladder for the Hrvatske vode (HV) hazard maps 2019: a) vector polygons,
b) point query (GetFeatureInfo), c) WMS overlay only. What was found:

- a) not available: the WFS of `servisi.voda.hr` is disabled (`2026-11-04_hv_wfs_*_GetCapabilities.xml`, an
  exception report), the CKAN package and the NIPP register list the WMS only, and no vector download exists.
- b) not available: all three 2019 hazard layers have `queryable="0"`, and GetFeatureInfo answers
  `LayerNotQueryable` (`2026-11-04_hv_getfeatureinfo_probe.json`, `2026-11-04_hv_flood_ladder_summary.json`).
- c) works: GetMap returns transparent PNG tiles and the service sends `access-control-allow-origin: *`
  (`2026-11-04_hv_wms_cors_probe.txt`), so the browser draws the layers directly.

Consequences: `/passport` returns `flood.level = null` and the message "Automatska procjena nije dostupna;
pogledajte kartu.", the three layers as WMS metadata, the HV disclaimer and the map year. **A class is never
derived from pixel colours.** The classification code (`flood_level`, `level_from_cell_shares`, scores 1.0 / 0.66 /
0.33 / 0) exists and is unit-tested, but receives real flags only if a vector or point-query source appears. The
municipal view therefore reports flood exposure as "nije dostupno" and priority is computed from the hazards that
have data, with the remaining weights renormalised to 1.

## Decision 2: Open-Meteo Climate API is cost-limited, so the national grid fills gradually

The free tier limits calls by **cost**, not count: `cost = series x days / 140` (measured: 939.2 for three models x
two variables x 21 915 days, header `x-ratelimit-cost`), against 600 per minute, 5 000 per hour and 10 000 per day
(pricing page, `2026-11-04_open_meteo_pricing_page.html`). A full address point (1991-2050) costs 939 as one request
or 783 as two; a grid point (future Tmax only) costs about 157. About ten full points fit into a day.

- The percentile reference is a national 0.25 degree lattice (125 points inside Croatia), fetched farthest-first so
  every prefix is a spatially even sample, by a resumable, quota-aware batch job (`otporno ingest heat-grid`).
  It keeps a reserve of 1 500 per day and 1 000 per hour and leaves the minute window empty for interactive use.
- An address is rounded to 0.1 degree and cached in `heat_point`. The interactive path uses one combined request
  (cost 939) so a cold passport is a single round trip; if the quota is exhausted the nearest stored full point
  within 25 km is used and flagged as approximate, otherwise the heat card says why it is unavailable.
- The number of grid points behind every percentile is shown, and confidence drops while the grid is thin.
- A request costing more than a window's limit is accepted by the server on an empty window (measured), so the
  client treats such a request as needing a clear window.

## Decision 3: cooling-centre candidates from OSM, Geofabrik as fallback

Candidates are public buildings (`amenity` library, school, community_centre, social_facility, townhall) from
Overpass; when Overpass fails the Geofabrik extract is read with `osmium`, as in ADR 0005 (no new dependency beyond
that ADR). There is no public register of existing cooling centres, so "covered before" is zero.

## Decision 4: cited action rules in YAML

`pyyaml` is the one new dependency of this app. Rules live in `config/action_rules.yaml` (66 rules: min band,
priority, Croatian text, a source id and the verbatim quote it rests on). Every cited page was opened on 2026-11-04.
Municipal heat and fire rules rest on laws and public health pages because no municipal cooling-centre page exists.

## Consequences

- Flood is the weakest part of the product and says so; the planned upgrade path is a vector source from HV.
- Karlovac and Zagreb heat data depend on how many days the batch job has run; `GET /health/climate-quota` shows
  usage and cached points.

## Addendum (P1, 2026-11-04)

- **Fire exposure from CORINE 2018.** The EEA map service answers `identify` point queries with the official class
  code (`2026-11-04_corine_identify_*.json`), so two queries per address (class at the point, classes within about
  500 m) replace a download. Band: inside classes 311-324 `visoka`, such vegetation within 500 m `umjerena`, else
  `niska`; confidence is always `niska` (minimum mapping unit 25 ha). It is an exposure, not a fire probability.
  It is not computed per municipal cell (thousands of requests), so the cell priority keeps fire weight 0 and
  renormalises, as for flood.
- **DHMZ current observations** (`vrijeme.hr/hrvatska_n.xml`, 60 stations on 2026-11-04): cached 30 minutes, hidden
  when older than 3 hours; a humidity of exactly 0 is treated as a sensor gap.
- **Municipal brief** is rendered with Jinja2 (`jinja2>=3`, the second new dependency of this app after `pyyaml`).
