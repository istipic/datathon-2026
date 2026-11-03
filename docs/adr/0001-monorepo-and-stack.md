# ADR 0001: Monorepo, one database server, SPAs

- Status: accepted
- Date: 2026-11-03

## Context

Three open-data apps (blizu, otporno, nabavaradar) are built for the Datathon Portala otvorenih
podataka 2026 (deadline 9 Nov 2026) by a very small team. They share data-portal access (CKAN),
provenance, geo utilities, error handling, deployment and UI conventions.

## Decisions

### One monorepo (uv workspace + pnpm workspace)

- Shared code (`opendata_core`, `@dt/ui`) changes together with its three consumers; a single PR
  can update a helper and all call sites, and one CI run proves nothing broke.
- No package publishing, versioning or cross-repo release choreography in a 5-day-scale schedule.
- One set of working rules, tooling and docs. Each app still builds and deploys independently
  (own API image, own SPA, own database).
- Cost accepted: all apps share the lockfiles and CI time; a broken core blocks all apps.

### One PostgreSQL server, three databases

- The apps are independent (separate schemas, extensions and migrations) but a datathon
  deployment is a single small host. One Postgres (16 + PostGIS 3.4 + pgvector) is one thing to
  run, back up (`make backup-db`) and monitor, and uses memory once instead of three times.
- Separate _databases_ (not schemas) keep extensions per app (pgvector only where needed) and
  make it impossible for one app's migration to touch another's tables.
- Cost accepted: a shared failure domain and shared resources; acceptable for this scale. Splitting
  later only needs a new `DATABASE_URL`.

### Single-page applications (React + Vite), static hosting

- All apps are interactive map/table explorers over an HTTP API; no content that needs server
  rendering or SEO beyond a landing page.
- A built SPA is static files: served by Caddy with strong caching, no Node process in production,
  and a strict CSP (`default-src 'self'`) is easy to keep.
- The API is a separate FastAPI service (`/api/v1`), so data logic stays in Python next to the
  geo/statistics libraries.
- Cost accepted: client-side routing needs the `try_files … /index.html` fallback and first load
  ships a JS bundle.

## Notes

- Caddy's CSP is the specified one plus `worker-src 'self' blob:` and `https://tile.openstreetmap.org`
  in `connect-src`: MapLibre runs tile workers from `blob:` URLs and the raster fallback fetches OSM
  tiles with `fetch()`. Without these the map cannot render under `default-src 'self'`. (Based on
  MapLibre's documented CSP requirements; not yet exercised in a real browser — verify in the first
  app that shows a map.)
