# FOUNDATION

Shared foundation for the three Datathon 2026 apps: **blizu**, **otporno**, **nabavaradar**.
Read this before changing anything (see [CLAUDE.md](../CLAUDE.md) for the working rules).

## Layout

```
packages/core   Python package `opendata_core` (src layout), tests in packages/core/tests
packages/ui     TypeScript package `@dt/ui` (tokens, Tailwind preset, React components)
apps/<app>/     api/ web/ data/ docs/   (empty until the app tasks)
infra/          db image, python-api.Dockerfile, web.Dockerfile
```

### Conventions the app tasks must follow

| Thing       | Convention                                                                                                                                                                    |
| ----------- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| API package | `apps/<app>/api` is a uv workspace member: dist `<app>-api`, import `<app>_api`                                                                                               |
| ASGI app    | `<app>_api.main:app`, built with `opendata_core.app_factory.create_app`                                                                                                       |
| Workspace   | add `apps/<app>/api` to `[tool.uv.workspace].members` in the root `pyproject.toml` (a glob fails while a folder has no `pyproject.toml`) and to `[tool.uv.sources]` if needed |
| Migrations  | `apps/<app>/api/alembic.ini` + `migrations/`; start from `opendata_core/alembic_template/` (`env.py.template`, `provenance_migration.py`)                                     |
| CLI         | `python -m <app>_api.cli ingest <step>` (typer) — used by `make ingest`                                                                                                       |
| Web package | `apps/<app>/web`, pnpm package named `<app>-web`, `build` script → `dist/`                                                                                                    |
| Evidence    | raw probe responses with date: `apps/<app>/data/evidence/<YYYY-MM-DD>_<name>.<ext>`                                                                                           |
| Fixtures    | `tests/fixtures/<source>/<YYYY-MM-DD>_<name>.<ext>` — REAL recorded responses only                                                                                            |
| Database    | one PostgreSQL server, DBs `blizu`, `otporno`, `nabavaradar`; PostGIS + pg_trgm everywhere, pgvector in blizu and nabavaradar                                                 |
| Tailwind    | `presets: [require('@dt/ui/tailwind-preset')]`; import `@dt/ui/styles.css`; override only `--brand-600/700`, `--accent-600`                                                   |
| HTML        | `<html lang="hr">`, all UI text in Croatian                                                                                                                                   |

## `opendata_core` modules

| Module                            | Purpose                                                     | Public API                                                                                                                                                |
| --------------------------------- | ----------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `config`                          | Settings from env / `.env`                                  | `CoreSettings` (`app_name, env, database_url, log_level, contact_email, http_cache_dir, http_timeout_s, nominatim_url, smtp_*, public_base_url, git_sha`) |
| `logging`                         | structlog (JSON in prod, pretty in dev) + `X-Request-ID`    | `configure_logging(settings)`, `RequestIDMiddleware`                                                                                                      |
| `http`                            | httpx client, retries, Retry-After, file cache, downloads   | `make_client`, `get_json`, `get_bytes`, `post_json`, `fetch` (→ `Fetched` with `retrieved_at`/`from_cache`), `download_file`, `user_agent`                |
| `db`                              | SQLAlchemy base, engine, FastAPI session dependency         | `Base`, `make_engine`, `make_session_dependency`                                                                                                          |
| `provenance`                      | `data_source` + `ingestion_run` tables, freshness summary   | `DataSource`, `IngestionRun`, `register_source`, `record_ingestion`, `sources_summary`, enums `AccessMethod/Tier/RunStatus`                               |
| `alembic_template`                | Reusable migration for core tables + `env.py.template`      | `provenance_migration.upgrade/downgrade`                                                                                                                  |
| `ckan`                            | data.gov.hr CKAN client (throttled ≤ 2 req/s)               | `CkanClient`, `status_show`, `package_show`, `package_search`, `resource_show`, `newest_resource`, `download`, `CkanError`, `BASE`                        |
| `geo`                             | CRS constants and geometry helpers                          | `WGS84`, `HTRS96_TM`, `to_metric`, `in_croatia`, `bbox_of_points`, `bbox_around`, `bbox_contains`, `haversine_m`, `snap_points_to_nodes`                  |
| `geocode`                         | Nominatim search, 1 req/s, 30-day DB cache (single lookups) | `search(session, q, settings=…, viewbox=, bounded=)`, `GeocodeCache`, `ATTRIBUTION`                                                                       |
| `popgrid`                         | Eurostat Census 2021 1 km grid, Croatia                     | `download_popgrid`, `read_croatia_cells`, `load_popgrid`, `popgrid_has_age_groups`, `has_age_groups`, `PopGridCell`, `parse_grd_id`, `cell_bounds_3035`   |
| `optimize`                        | Greedy maximum-coverage solver                              | `greedy_mclp(demand, coverage, k, already_covered=None)`                                                                                                  |
| `semantic` _(extra `[semantic]`)_ | multilingual-e5-small embeddings (384-d, normalised)        | `encode_queries`, `encode_passages`, `MODEL`, `DIM`                                                                                                       |
| `email`                           | SMTP (STARTTLS on 587) + Jinja2 templates                   | `send_email`, `make_template_env`, `render_email`                                                                                                         |
| `errors`                          | RFC 7807 problem+json handlers                              | `register_exception_handlers`, `problem`                                                                                                                  |
| `health`                          | `/health` and `/api/v1/sources`                             | `make_health_router(get_session, settings)`                                                                                                               |
| `app_factory`                     | FastAPI app wiring                                          | `create_app(settings, routers, cors_origins, get_session=None, title=None)`                                                                               |

Notes that matter when using them:

- **Retrieval time is always exposed.** `http.fetch` returns `Fetched.retrieved_at`; cached responses keep their _original_ time and `from_cache=True`. `geocode.search` returns `fetched_at`/`from_cache`.
- **`freshness_days`** (in `/api/v1/sources`) is the age of the _data_: days since `source_last_modified` if the publisher reports it, otherwise days since retrieval. `retrieved_at` is always given next to it.
- **popgrid**: source verified 2026-11-03 (evidence: `packages/core/data/evidence/2026-11-03_eurostat_census_grid_V3*`). Fields loaded: total + under-15 + 15–64 + 65+. `-8888`/`-9999` become `NULL`. Cells shared with SI/HU (`CNTR_ID` like `HR-SI`) also include neighbours' residents, so totals slightly exceed the national census count. Apps must call `popgrid_has_age_groups()` and fall back to total population if it is `False`.
- **geocode** is for single lookups only (Nominatim policy). Never loop over datasets with it.
- **Rate limit**: 60/minute per client IP, one budget across all routes (`PerIPRateLimitMiddleware`; see ADR 0004). Behind Caddy the API runs with `--proxy-headers`.
- **Errors**: prod responses never contain exception text or stack traces; dev responses include a `traceback` field.

## `@dt/ui` components

`AppShell`, `MapView`, `SourceBadge`, `FreshnessChip`, `ConfidenceBadge`, `LoadingSkeleton`, `EmptyState`, `ErrorState`, `DataSourcesPage`, `SkipLink` (+ `fetchSources`, `ApiError`, formatting helpers). All user-facing text is Croatian.

- `MapView` defaults to OpenFreeMap "liberty", falls back to OSM raster tiles if the style cannot load (and says so), and always shows "© OpenStreetMap contributors". It is unit-tested against a fake maplibre-gl only (jsdom has no WebGL) — verify visually in a real browser in each app.
- `DataSourcesPage` needs a `QueryClientProvider` above it and an API that serves `GET /api/v1/sources`.
- Colour is never the only carrier of meaning (chips carry text + glyph). Token contrast is asserted by `tokens.test.ts`.

## Conventions

- **API prefix** `/api/v1`; `/health` is unversioned.
- **Errors** are `application/problem+json` (RFC 7807): `type, title, status, detail, instance, request_id` (+ `errors` for 422).
- **Timestamps**: UTC, ISO 8601 (`2026-11-03T18:31:50+00:00`). Format for display in the UI only (Europe/Zagreb).
- **GeoJSON** RFC 7946: coordinates are `[lon, lat]` (WGS 84). Metric work in HTRS96/TM (EPSG:3765).
- **Provenance rule**: every table loaded from an external source has a `data_source` row and an `ingestion_run` row (`register_source` + `record_ingestion`).
- **Fixture rule**: tests use recorded REAL responses at `tests/fixtures/<source>/<YYYY-MM-DD>_<name>.<ext>`; no invented sample data in production code paths.
- **Secrets** only in `.env` (gitignored); keep `.env.example` current; never log secrets.
- Use `127.0.0.1`, not `localhost`, for the dev DB/SMTP on Windows (IPv6 fallback can stall for ~40 s per connection).

## Testing

| Command                                                                        | What                                                       |
| ------------------------------------------------------------------------------ | ---------------------------------------------------------- |
| `uv run pytest packages/core`                                                  | unit tests, no network; coverage gate 80 %                 |
| `RUN_LIVE=1 CONTACT_EMAIL=you@x.hr uv run pytest -m live packages/core`        | real-network smoke (CKAN `status_show`, records a fixture) |
| `TEST_DATABASE_URL=… uv run pytest packages/core`                              | also runs `db` tests (PostGIS load, Alembic template)      |
| `uv run --package opendata-core --extra semantic pytest -m slow packages/core` | real e5 model test (downloads ~470 MB)                     |
| `pnpm -r test`                                                                 | vitest (jsdom) for `@dt/ui`                                |

## Deployment

`docker-compose.prod.yml` + `Caddyfile`: Caddy serves `/srv/<app>` (SPA with `try_files {path} /index.html`) and proxies `/api/*` and `/health` to `<app>-api:8000`. The CSP is the specified one **plus** `worker-src 'self' blob:` and `https://tile.openstreetmap.org` in `connect-src`, which MapLibre needs (see ADR 0001 notes). `make deploy DEPLOY_HOST=user@host` runs `git pull`, `compose pull`, `compose up -d --build` over ssh.
