# syntax=docker/dockerfile:1
# Build context: repository root.   docker build -f infra/web.Dockerfile --build-arg APP=blizu .
#
# Convention: apps/<APP>/web is a pnpm workspace package named "<APP>-web" with a `build` script
# producing apps/<APP>/web/dist. The final image only holds the static files; docker-compose.prod.yml
# runs it once to copy them into the volume that Caddy serves from /srv/<APP>.

FROM node:20-slim AS build
RUN corepack enable
WORKDIR /repo
ARG APP
COPY package.json pnpm-workspace.yaml pnpm-lock.yaml ./
COPY packages/ui packages/ui
COPY apps/${APP}/web apps/${APP}/web
RUN test -f "apps/${APP}/web/package.json" \
    || (echo "ERROR: apps/${APP}/web/package.json not found (the app web task has not run yet)" && exit 1)
RUN pnpm install --frozen-lockfile --filter "${APP}-web..."
RUN pnpm --filter "${APP}-web" build

FROM busybox:1.37 AS dist
ARG APP
ENV APP=${APP}
COPY --from=build /repo/apps/${APP}/web/dist /dist
# One-shot: publish the SPA into the shared volume mounted at /srv
CMD ["sh", "-c", "mkdir -p /srv/$APP && rm -rf /srv/$APP/* && cp -r /dist/. /srv/$APP/"]
