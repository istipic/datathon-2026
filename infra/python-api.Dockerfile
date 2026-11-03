# syntax=docker/dockerfile:1
# Build context: repository root.   docker build -f infra/python-api.Dockerfile --build-arg APP=blizu .
#
# Convention for an app API (added by the app tasks): uv workspace member apps/<APP>/api with the
# distribution name "<APP>-api", importable package "<APP>_api" and ASGI app "<APP>_api.main:app".
# Until the app exists the image still builds with opendata_core only (and fails clearly at start).

FROM python:3.12-slim AS builder
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv
ENV UV_LINK_MODE=copy UV_COMPILE_BYTECODE=1 UV_PYTHON_DOWNLOADS=never
WORKDIR /app

ARG APP
# Optional extras of the app API, e.g. --build-arg UV_SYNC_ARGS="--extra semantic" (Blizu /search model)
ARG UV_SYNC_ARGS=""
COPY pyproject.toml uv.lock README.md .python-version ./
COPY packages/core packages/core
# apps/<APP>/api may only hold a .gitkeep yet
COPY apps/${APP}/api apps/${APP}/api
# Workspace members other than core and <APP>-api are not needed; uv.lock still lists them.
RUN if [ -f "apps/${APP}/api/pyproject.toml" ]; then \
      uv sync --frozen --no-dev --no-editable --package "${APP}-api" ${UV_SYNC_ARGS}; \
    else \
      echo "NOTE: apps/${APP}/api/pyproject.toml missing - installing opendata-core only"; \
      uv sync --frozen --no-dev --no-editable --package opendata-core; \
    fi

FROM python:3.12-slim AS runtime
ARG APP
ENV APP=${APP} \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    ENV=prod
RUN groupadd --system app && useradd --system --gid app --home-dir /app app
WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv /app/.venv
# Migrations / data folders used by `make migrate` and `make ingest` inside the container
COPY --chown=app:app apps/${APP}/api /app/api
# Writable data directory (raw downloads, derived graph/arrays): mount a named volume here.
ENV DATA_DIR=/data HF_HOME=/data/hf
RUN mkdir -p /data && chown app:app /data
VOLUME /data
USER app
EXPOSE 8000
HEALTHCHECK --interval=15s --timeout=5s --start-period=20s --retries=5 \
  CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=4).status == 200 else 1)"
# --proxy-headers: Caddy is the only client inside the network, so trusting X-Forwarded-For is safe;
# it makes the per-IP rate limit see real client addresses.
CMD ["sh", "-c", "exec uvicorn ${APP}_api.main:app --host 0.0.0.0 --port 8000 --proxy-headers --forwarded-allow-ips='*'"]
