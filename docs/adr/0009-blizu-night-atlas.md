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
- 3D: see the section "3D buildings" at the end of this file (filled in after the tile check).

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
