# ADR 0002: Install pgvector from the PGDG archive

- Status: accepted
- Date: 2026-11-03

## Context

The specified database image is `postgis/postgis:16-3.4` plus
`apt-get install postgresql-16-pgvector`. On 2026-11-03 that tag is based on **Debian 11
(bullseye)**, and `apt-get update` fails with
`The repository 'http://apt.postgresql.org/pub/repos/apt bullseye-pgdg Release' does not have a Release file`
because PGDG no longer serves bullseye from the main apt host. A newer tag (`16-3.4-bookworm`) does not exist.

## Decision

Keep the specified base image and install command, but first rewrite the image's own
`/etc/apt/sources.list.d/pgdg.list` to the official PGDG archive
(`https://apt-archive.postgresql.org/pub/repos/apt/`), which still holds `bullseye-pgdg`
(same signing key). Result: `pgvector 0.8.6` on PostgreSQL 16.4 / PostGIS 3.4.3.

## Consequences

- The build is reproducible only while the archive stays online; it is an archive, so that is expected.
- The base image receives no more Debian bullseye security updates. Before any public deployment,
  consider moving to a newer `postgis/postgis` tag (e.g. `16-3.5`/`16-3.6`, which are available) and
  re-testing the extensions — a one-line change in `infra/db/Dockerfile`.
