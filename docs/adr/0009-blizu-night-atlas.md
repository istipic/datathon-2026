# ADR 0009: Blizu v2 "Night Atlas" (dark UI, Inter, dark base map, map animation engine)

- Status: accepted
- Date: 2026-11-05

## Context

Blizu got a dark, cinematic redesign with live map choreography (walking-time flood, route that draws itself,
planner columns that sink). The decisions below are the ones that are not obvious from the code.

## Decision 1: Inter Variable, self-hosted (`@fontsource-variable/inter`)

- The production CSP (`Caddyfile`) is `default-src 'self'`, so the font is bundled by Vite from the npm package, not
  loaded from a CDN. Only the `latin` and `latin-ext` WOFF2 files are referenced (two `@font-face` rules in
  `apps/blizu/web/src/index.css`, with the package's `unicode-range`); together they cover Croatian č ć š ž đ.
- Licence: SIL Open Font License 1.1 (package `LICENSE`). It is the only new dependency of the redesign.
- `font-feature-settings: "tnum" 1, "cv11" 1` gives tabular numbers; numeric elements also carry `.num`/`.dt-num`.
- `@dt/ui` keeps IBM Plex for Otporko and Birokratko; Blizu overrides `--font-sans`/`--font-mono` only in its own CSS,
  so the Plex files are never requested by Blizu pages.

## Decision 2: tokens are overridden in Blizu's `index.css` only

The `@dt/ui` neutral scale is inverted and the semantic slots (`--bg`, `--fg`, `--border`, `--link`, status colours)
are mapped to the Night Atlas palette, so shared components (ErrorState, DataSourcesPage, chips) render correctly on
the dark canvas without touching the other apps. `scripts/contrast.mjs` reads the real stylesheet and fails below
4.5:1 for text and 3:1 for control borders and large text; `src/lib/contrast.test.ts` runs it in vitest (55 pairs).
Print stays a light A4 card: the `@media print` block restores the light tokens.

## Decision 3: dark base style and 3D buildings

- Base style: `https://tiles.openfreemap.org/styles/dark` (HTTP 200, 47 layers, vector source
  `https://tiles.openfreemap.org/planet`; evidence `apps/blizu/data/evidence/2026-11-05_openfreemap_dark_style*.json`).
  It has no `fill-extrusion` layer. It is passed through `MapView`'s existing `styleUrl`; if the vector style fails,
  `MapView` falls back to OSM raster tiles (new optional `onFallback` callback lets Blizu disable 3D and show a notice).
- 3D: see the section "3D buildings" below.

## Decision 4: animation engine of our own (no animation libraries)

`apps/blizu/web/src/lib/anim/` is ~300 lines: one time-based `requestAnimationFrame` clock (pauses when the tab is
hidden or the map is off screen, never runs under `prefers-reduced-motion`), easings, timelines, camera presets, route
geometry and a scene state machine synchronised with the URL (`?scena=`). Per-frame values live in refs and MapLibre
setters, never in React state. MapLibre does not transition data-driven paint properties, so before/after values are
animated by an expression driven by the clock.

## Decision 5: API contracts behind the animations

`GET /api/v1/isochrone`, `GET /api/v1/route` and `cells` in `POST /api/v1/plan/optimise` are documented in
`apps/blizu/docs/README.md`. Every animated number (flood front, facility minutes, route length, column heights) comes
from these responses; decorative motion carries no data and is commented `// decorative`.

## 3D buildings

The dark style has no `fill-extrusion` layer, so Blizu adds one (`BuildingsLayer` in `lib/anim/layers.ts`) on the
style's own vector source `openmaptiles`, source-layer `building`, below the first symbol layer. Height and base come
from the tiles' `render_height` / `render_min_height`; features with `hide_3d: true` (parts drawn elsewhere) are skipped.

Verified on 2026-11-05 in the real tiles over Trg bana Jelačića (`scripts/buildings-check.mjs`, evidence
`apps/blizu/data/evidence/2026-11-05_openfreemap_building_heights.json`): all 136 rendered building features carry both
attributes (median 11 m, maximum 108 m). The opacity is a constant paint property, so the native paint transition fades
the buildings in (data-driven properties do not transition in MapLibre; the planner columns are animated by an expression
driven by the clock instead). On the raster fallback there are no buildings and the 3D scene is disabled with a notice.

## Known limitation: mobile Lighthouse performance of `/kartica`

The results page now puts the map above the fold. Lighthouse (mobile, 4x CPU throttling, software WebGL) scores
performance 43-50 there (home 94, planner 88; accessibility 100 on all three). A CPU profile shows the time is native
rendering and MapLibre; the application's own scripting is about 100 ms. With a GPU the scenes run at about 177-180 fps
(`apps/blizu/data/evidence/2026-11-05_blizu_fps_gpu.json`).

## Revision (2026-11-05, after review): light, Google-Maps-like look

The first version was dark with a cyan/violet accent. After review the UI was switched to a light, professional look
close to Google Maps (palette: white surfaces, `#F8F9FA` canvas, text `#202124`, muted `#5F6368`, blue `#1967D2`,
green far-end `#188038`, red pin and sites `#D93025`; 8 px radii, flat blue buttons, hairline borders, the Google
elevation shadow; no gradients, glows or purple). The base map is now OpenFreeMap `liberty`
(`2026-11-05_openfreemap_liberty_style*.json`, HTTP 200, 111 layers), which already contains the `building-3d`
extrusion layer, so the 3D scene fades that layer in instead of adding its own (our own layer remains as a fallback
for styles without one). The walking-time ramp is now blue near the address and green far away, the moving front is
orange; the planner ramp is a five-step blue scale. Animations, API contracts and behaviour are unchanged; the contrast
script checks the new palette (55 pairs). The sidebar of the results page is 540 px (planner 630 px), narrowing
proportionally on small windows. The "dark" sections above describe the first version.
