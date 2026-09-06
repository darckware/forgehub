#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

export FORGEHUB_VERSION="$(cat VERSION)"
export FORGEHUB_GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
export FORGEHUB_BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

docker compose build

# Compose now gives each freshly built service a stable `:latest` name.
# `docker compose images -q` inspects the images of currently running
# containers, which can still point at a deleted pre-build image and is not
# a reliable source for tagging a new build.
docker tag "forgehub-backend:latest" "forgehub-backend:${FORGEHUB_VERSION}"
docker tag "forgehub-frontend:latest" "forgehub-frontend:${FORGEHUB_VERSION}"

echo "Built ForgeHub ${FORGEHUB_VERSION} @ ${FORGEHUB_GIT_SHA}"
