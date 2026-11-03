# CLAUDE.md — datathon-2026

Monorepo for three open-data apps (blizu, otporno, nabavaradar) for the Croatian
"Datathon Portala otvorenih podataka 2026". Submission deadline: 9 Nov 2026.

## WORKING RULES (apply to every task)

1. Inspect before changing: run `git status`, list the tree (depth 3), read docs/FOUNDATION.md and the app's docs/ before editing.
2. Preserve working functionality. No rewrites of working code unless a test proves a defect.
3. Implement in small steps. After each meaningful step run the relevant tests and commit (Conventional Commits).
4. Never invent API endpoints, parameters, field names, credentials, datasets or data values. Probe the real source, save evidence (raw response with date) under apps/<app>/data/evidence/, then code against it. If a source cannot be verified, implement the fallback specified in the task and report it.
5. No fake, sample or demo data in production code paths. Tests use recorded REAL responses saved as tests/fixtures/<source>/<YYYY-MM-DD>_<name>.<ext>. Never present cached or stale data as live: always expose retrieval time.
6. Every table loaded from an external source has a data_source row and an ingestion_run row (opendata_core.provenance).
7. Do not add dependencies beyond the fixed stack unless essential; if you add one, record why in docs/adr/.
8. Secrets only in .env (gitignored); keep .env.example current; never print secrets in logs.
9. UI text in Croatian (hr), code and comments in English.
10. Never claim something works without running it. End every task with a REPORT: Implemented / Verified (exact commands + results) / Not done / Fallbacks used / Known issues.
11. Respect source usage policies: identifying User-Agent with contact email, rate limits, caching.

## Quick reference

- Foundation docs: docs/FOUNDATION.md (modules, conventions). Decisions: docs/adr/.
- Python: uv workspace (`uv sync`, `uv run pytest packages/core`). Core package: `opendata_core`.
- Web: pnpm workspace (`pnpm -r build`, `pnpm -r test`). Shared UI: `@dt/ui`.
- Local infra: `make dev` (PostgreSQL 16 + PostGIS + pgvector, Mailpit).
