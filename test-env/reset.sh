#!/usr/bin/env bash
# Reset the isolated test database: drop and recreate the `company` and
# `public` schemas, then migrate to Alembic head (Plano Integrado T.1).
#
#   ./test-env/reset.sh
#
# The work is done by backend/app/scripts/reset_test_database.py, which
# refuses before connecting unless ENVIRONMENT=test and the target is
# forgehub_test@127.0.0.1:5439, and after connecting still refuses a server
# that hosts a `forgehub` database. Runs in the test tools container, so it
# never reads the repo-root .env.
#
# POSTGRES_* variables set in the caller's environment are passed through on
# purpose: pointing them anywhere else must make the reset refuse, never
# silently fall back to the test target.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

if [ ! -f "$DIR/.env.test" ]; then
  echo "test-env/.env.test is missing -- run test-env/init-env.sh first." >&2
  exit 1
fi

passthrough=()
for var in ENVIRONMENT POSTGRES_HOST POSTGRES_PORT POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD POSTGRES_SCHEMA; do
  if [ -n "${!var+x}" ]; then
    passthrough+=(-e "$var")
  fi
done

exec docker compose -f "$DIR/docker-compose.yml" run --rm -T "${passthrough[@]}" \
  tools python -m app.scripts.reset_test_database
