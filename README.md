# datathon-2026

Shared foundation for three open-data apps built for the Croatian **Datathon Portala otvorenih
podataka 2026** (submission deadline: 9 Nov 2026):

| App           | Folder             |
| ------------- | ------------------ |
| `blizu`       | `apps/blizu`       |
| `otporno`     | `apps/otporno`     |
| `nabavaradar` | `apps/nabavaradar` |

This repository currently contains the **foundation only** (no app business logic): the Python
package `opendata_core`, the UI package `@dt/ui`, the database/Docker/Caddy infrastructure and CI.

- Working rules for every task: [CLAUDE.md](CLAUDE.md)
- Modules, conventions, testing, deployment: [docs/FOUNDATION.md](docs/FOUNDATION.md)
- Decisions: [docs/adr/](docs/adr/)

## Quick start

Requirements: Docker, [uv](https://docs.astral.sh/uv/) (Python 3.12), Node 20 + pnpm 9, make.

```bash
cp .env.example .env          # set POSTGRES_PASSWORD (and CONTACT_EMAIL for external APIs)
make dev                      # PostgreSQL 16 + PostGIS + pgvector, Mailpit (http://127.0.0.1:8025)

uv sync                       # Python workspace
pnpm install                  # web workspace

make test                     # pytest (no network) + vitest
make lint                     # ruff, mypy, eslint, prettier
make build                    # type-check + bundle web packages
```

On Windows run `make` from Git Bash. Use `127.0.0.1` (not `localhost`) in `DATABASE_URL`/`SMTP_HOST`.

## Layout

```
packages/core   opendata_core (config, http, provenance, ckan, geo, geocode, popgrid, optimize,
                semantic, email, errors, health, app_factory)
packages/ui     @dt/ui (tokens, Tailwind preset, accessible React components)
apps/<app>/     api/ web/ data/ docs/  (filled by the app tasks)
infra/          db image, python-api.Dockerfile, web.Dockerfile
```

## Licence

Source code: [EUPL-1.2](LICENSE). Data sources keep their own licences; the apps list them on the
"Izvori podataka" page (`GET /api/v1/sources`).
