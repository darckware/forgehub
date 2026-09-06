#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

export FORGEHUB_VERSION="$(cat VERSION)"
export FORGEHUB_GIT_SHA="$(git rev-parse --short HEAD 2>/dev/null || echo unknown)"
export FORGEHUB_BUILD_DATE="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

docker compose build

backend_image="$(docker compose images -q forgehub-backend)"
frontend_image="$(docker compose images -q forgehub-frontend)"
docker tag "$backend_image" "forgehub-backend:${FORGEHUB_VERSION}"
docker tag "$frontend_image" "forgehub-frontend:${FORGEHUB_VERSION}"

echo "Built ForgeHub ${FORGEHUB_VERSION} @ ${FORGEHUB_GIT_SHA}"
