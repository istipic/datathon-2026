# datathon-2026 developer commands. Requires: docker compose, uv, Node 20 + pnpm, make.
# On Windows run make from Git Bash (and put Node/pnpm on PATH).

SHELL := /bin/bash
.DEFAULT_GOAL := help

COMPOSE      ?= docker compose
PROD_COMPOSE ?= docker compose -f docker-compose.prod.yml
APP          ?=
STEP         ?=
DEPLOY_HOST  ?=
DEPLOY_DIR   ?= /opt/datathon-2026
PROD         ?=
APPS         := blizu otporno nabavaradar

require-app = $(if $(filter $(APP),$(APPS)),,$(error APP must be one of: $(APPS)  (usage: make $@ APP=blizu)))

.PHONY: help dev down test lint build migrate ingest deploy backup-db

help: ## Show this help
	@grep -E '^[a-z-]+:.*## ' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  make %-10s %s\n", $$1, $$2}'

dev: ## Start PostgreSQL (PostGIS+pgvector) and Mailpit; wait until healthy
	@test -f .env || (echo "ERROR: .env missing - copy .env.example to .env and set POSTGRES_PASSWORD" && exit 1)
	$(COMPOSE) up -d --build --wait
	@echo "db: 127.0.0.1:5432   mailpit UI: http://127.0.0.1:8025"

down: ## Stop the dev stack (data volume is kept)
	$(COMPOSE) down

test: ## Python (no live network) and web tests
	uv run pytest packages/core
	uv run pytest apps/blizu/api
	uv run pytest apps/nabavaradar/api
	pnpm -r test

lint: ## ruff, mypy, eslint, prettier
	uv run ruff check .
	uv run ruff format --check .
	uv run mypy packages/core
	pnpm -r lint
	pnpm exec prettier --check .

build: ## Build all web packages (type-check + bundle)
	pnpm -r build

migrate: ## Run Alembic migrations of one app:  make migrate APP=blizu   (PROD=1: in the prod container)
	$(require-app)
ifeq ($(PROD),1)
	$(PROD_COMPOSE) run --rm $(APP)-api alembic -c /app/api/alembic.ini upgrade head
else
	uv run --package $(APP)-api alembic -c apps/$(APP)/api/alembic.ini upgrade head
endif

ingest: ## Run an ingestion step:  make ingest APP=blizu STEP=all   (PROD=1: prod container, then restart the API)
	$(require-app)
	@test -n "$(STEP)" || (echo "ERROR: STEP is required (usage: make ingest APP=blizu STEP=<step>)" && exit 1)
ifeq ($(PROD),1)
	$(PROD_COMPOSE) run --rm $(APP)-api python -m $(APP)_api.cli ingest $(STEP)
	$(PROD_COMPOSE) restart $(APP)-api
else
	uv run --package $(APP)-api python -m $(APP)_api.cli ingest $(STEP)
endif

deploy: ## Update the server: ssh, git pull, compose pull/up   make deploy DEPLOY_HOST=user@server
	@test -n "$(DEPLOY_HOST)" || (echo "ERROR: set DEPLOY_HOST=user@server" && exit 1)
	ssh $(DEPLOY_HOST) 'cd $(DEPLOY_DIR) && git pull --ff-only && $(PROD_COMPOSE) pull --ignore-buildable && GIT_SHA=$$(git rev-parse --short HEAD) $(PROD_COMPOSE) up -d --build --remove-orphans'

backup-db: ## Dump the three databases to backups/<timestamp>/*.dump (pg_dump custom format)
	@mkdir -p backups/$$(date -u +%Y%m%dT%H%M%SZ)
	@dir=backups/$$(ls -1 backups | tail -1); \
	for d in $(APPS); do \
	  echo "dumping $$d -> $$dir/$$d.dump"; \
	  $(COMPOSE) exec -T db pg_dump -U postgres -Fc $$d > $$dir/$$d.dump || exit 1; \
	done; ls -la $$dir
