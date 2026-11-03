FROM postgis/postgis:16-3.4

# The base image is Debian 11 (bullseye). PGDG removed bullseye from apt.postgresql.org, so
# point apt at the official PGDG archive (same packages, same signing key) before installing.
# See docs/adr/0002-pgdg-archive-for-pgvector.md.
RUN sed -i 's|http://apt.postgresql.org/pub/repos/apt/|https://apt-archive.postgresql.org/pub/repos/apt/|' \
        /etc/apt/sources.list.d/pgdg.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends postgresql-16-pgvector \
    && rm -rf /var/lib/apt/lists/*

# Scripts in this directory run once, on first start of an empty data volume.
COPY init/ /docker-entrypoint-initdb.d/
