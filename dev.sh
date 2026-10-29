#!/usr/bin/env bash
# Dev-mode launcher for ForgeHub: hot-reload backend (uvicorn --reload) +
# frontend (vite dev), on ports separate from the Docker deploy (8000/4173)
# so both can run side by side. Docker only changes when someone explicitly
# runs `docker compose up -d --build` -- this script never touches it.
#
# Usage:
#   ./dev.sh [start] [--prod-db]   start (or restart if already running)
#   ./dev.sh restart [--prod-db]   stop + start
#   ./dev.sh stop                  stop both dev servers
#   ./dev.sh status                show whether they're up + which database
#
# Database (Plano Integrado T.1, 2026-10-28): the dev backend runs against
# the isolated test Postgres by default -- `forgehub_test` on 127.0.0.1:5439,
# test-env/docker-compose.yml -- with ENVIRONMENT=test, so it never reads
# the repo-root .env and app/core/config.py refuses any other database.
# dev.sh creates test-env/.env.test, starts the container and migrates it
# when needed. The test database starts empty (fictitious seed is T.2).
# `--prod-db` restores the previous behavior -- the dev backend on the real
# `forgehub_postgres` data, through .env -- and says so loudly.
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
TEST_ENV_DIR="$ROOT_DIR/test-env"
STATE_DIR="$ROOT_DIR/.dev"
LOG_DIR="$STATE_DIR/logs"
BACKEND_PID_FILE="$STATE_DIR/backend.pid"
FRONTEND_PID_FILE="$STATE_DIR/frontend.pid"
DB_MODE_FILE="$STATE_DIR/db_mode"

DB_MODE="test"
COMMAND=""
for arg in "$@"; do
  case "$arg" in
    --prod-db) DB_MODE="prod" ;;
    -*) echo "Unknown option: $arg"; echo "Usage: $0 [start|stop|restart|status] [--prod-db]"; exit 1 ;;
    *) [ -z "$COMMAND" ] && COMMAND="$arg" || { echo "Usage: $0 [start|stop|restart|status] [--prod-db]"; exit 1; } ;;
  esac
done
COMMAND="${COMMAND:-start}"

BACKEND_PORT=8001
FRONTEND_PORT=5172

mkdir -p "$LOG_DIR"

color() { printf "\033[%sm%s\033[0m" "$1" "$2"; }
ok()    { echo "$(color 32 "✓") $1"; }
warn()  { echo "$(color 33 "!") $1"; }
err()   { echo "$(color 31 "✗") $1"; }
info()  { echo "$(color 36 "→") $1"; }

pid_alive() {
  local pid="$1"
  [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null
}

port_owner_pids() {
  lsof -tiTCP:"$1" -sTCP:LISTEN 2>/dev/null
}

# uvicorn --reload forks a worker subprocess that ends up on a different pid
# than the one `$!` captures for the supervisor, and vite's `npm run dev`
# wrapper similarly isn't the pid actually bound to the port -- so "stop"
# targets whoever is really listening on the port, plus the recorded
# supervisor pid for good measure, rather than trusting one pid to own it.
stop_by_port() {
  local name="$1" port="$2" pid_file="$3"
  local pids
  pids=$( { port_owner_pids "$port"; [ -f "$pid_file" ] && cat "$pid_file"; } | sort -u)
  rm -f "$pid_file"
  if [ -z "$pids" ]; then
    warn "$name not running"
    return
  fi
  for pid in $pids; do
    pid_alive "$pid" && kill -TERM "$pid" 2>/dev/null
  done
  for _ in $(seq 1 20); do
    port_owner_pids "$port" >/dev/null 2>&1 || break
    [ -z "$(port_owner_pids "$port")" ] && break
    sleep 0.2
  done
  for pid in $(port_owner_pids "$port"); do
    kill -9 "$pid" 2>/dev/null
  done
  ok "Stopped $name"
}

cmd_stop() {
  stop_by_port "backend" "$BACKEND_PORT" "$BACKEND_PID_FILE"
  stop_by_port "frontend" "$FRONTEND_PORT" "$FRONTEND_PID_FILE"
}

prod_db_warning() {
  echo
  echo "$(color '1;41;97' "  !!! --prod-db: the dev backend will use the PRODUCTION database (forgehub_postgres, real data) !!!  ")"
  warn "Every write from this dev session lands in production. Drop --prod-db to go back to the test database."
  echo
}

# Test database: env file, container and schema, each created only when
# missing. Runs after the venv check, since migrating needs backend/.venv.
prepare_test_db() {
  if [ ! -f "$TEST_ENV_DIR/.env.test" ]; then
    bash "$TEST_ENV_DIR/init-env.sh" || { err "Could not create test-env/.env.test"; exit 1; }
  fi
  info "Ensuring the test Postgres (forgehub_test_postgres, 127.0.0.1:5439) is up ..."
  docker compose -f "$TEST_ENV_DIR/docker-compose.yml" up -d --wait forgehub_test_postgres >/dev/null 2>&1 \
    || { err "Test Postgres didn't come up healthy -- check: docker compose -f test-env/docker-compose.yml logs"; exit 1; }
  (cd "$BACKEND_DIR" && ENVIRONMENT=test .venv/bin/alembic upgrade head >>"$LOG_DIR/backend.log" 2>&1) \
    || { err "Migrating the test database failed -- check $LOG_DIR/backend.log"; exit 1; }
  ok "Test database ready (forgehub_test at Alembic head)"
}

check_config() {
  local failed=0

  if [ "$DB_MODE" = "prod" ] && [ ! -f "$ROOT_DIR/.env" ]; then
    err ".env not found at repo root -- --prod-db needs it (copy .env.example and fill in Postgres credentials)."
    failed=1
  fi

  # Checking that uvicorn exists isn't enough: a venv whose interpreter was
  # removed underneath it (the uv-managed python3.11 it symlinks to got
  # uninstalled, 2026-09-23) still has every script, so the old
  # `-x .venv/bin/uvicorn` check passed and the backend just failed to start.
  # Actually run the interpreter, and rebuild the venv when it can't.
  # Also rebuilt when it runs a different minor than the Docker image, so a
  # Python upgrade reaches every dev machine on its next ./dev.sh start.
  local py_minor="3.13"  # keep in sync with backend/Dockerfile's FROM python:<minor>-slim
  if [ ! -x "$BACKEND_DIR/.venv/bin/uvicorn" ] \
    || ! "$BACKEND_DIR/.venv/bin/python" -c "import sys; sys.exit(f'{sys.version_info[0]}.{sys.version_info[1]}' != '$py_minor')" >/dev/null 2>&1; then
    warn "backend/.venv missing, broken or not Python $py_minor -- (re)creating it and installing requirements (takes a bit)."
    rm -rf "$BACKEND_DIR/.venv"
    if command -v uv >/dev/null 2>&1; then
      { uv python install "$py_minor" >/dev/null 2>&1 \
        && uv venv -q --python "$py_minor" "$BACKEND_DIR/.venv" \
        && uv pip install -q --python "$BACKEND_DIR/.venv/bin/python" -r "$BACKEND_DIR/requirements.txt" -r "$BACKEND_DIR/requirements-dev.txt"; } \
        || { err "Failed to create backend venv with uv"; failed=1; }
    else
      python3 -m venv "$BACKEND_DIR/.venv" || { err "Failed to create backend venv"; failed=1; }
      "$BACKEND_DIR/.venv/bin/pip" install -q -r "$BACKEND_DIR/requirements.txt" || { err "pip install failed"; failed=1; }
    fi
  fi

  if [ ! -x "$FRONTEND_DIR/node_modules/.bin/vite" ]; then
    warn "frontend/node_modules missing or incomplete -- running npm install (first run only, takes a bit)."
    (cd "$FRONTEND_DIR" && npm install --silent) || { err "npm install failed"; failed=1; }
  fi

  if [ "$failed" -ne 0 ]; then
    err "Config checks failed -- fix the above before starting."
    exit 1
  fi
  ok "Config checks passed (backend venv, frontend deps)"
  if [ "$DB_MODE" = "test" ]; then
    prepare_test_db
  fi
}

start_backend() {
  local existing
  existing=$(port_owner_pids "$BACKEND_PORT")
  if [ -n "$existing" ]; then
    if [ -f "$BACKEND_PID_FILE" ]; then
      local running_mode
      running_mode=$(cat "$DB_MODE_FILE" 2>/dev/null || echo "unknown")
      ok "Backend already running on :$BACKEND_PORT (database: $running_mode)"
      [ "$running_mode" != "$DB_MODE" ] && warn "Requested database is '$DB_MODE' -- use ./dev.sh restart$([ "$DB_MODE" = prod ] && echo ' --prod-db') to switch."
      return
    fi
    err "Port $BACKEND_PORT is already in use (pid(s): $existing) by something dev.sh didn't start -- stop it manually first."
    exit 1
  fi
  info "Starting backend (uvicorn --reload) on :$BACKEND_PORT ..."
  local environment_override=""
  local pg_override=""
  if [ "$DB_MODE" = "test" ]; then
    # Settings read test-env/.env.test (127.0.0.1:5439) and never .env.
    environment_override="test"
  else
    prod_db_warning
    # .env's POSTGRES_HOST is the Docker container name (right for the deployed
    # backend on foundation_network), which the host itself can't resolve --
    # the dev backend then ran with every DB-backed loop failing on DNS. The
    # container publishes its port on 127.0.0.1, so use that instead whenever
    # the configured name doesn't resolve here. Only this process's env is
    # changed; .env stays as the Docker deploy needs it.
    local pg_host
    pg_host=$(grep -E '^POSTGRES_HOST=' "$ROOT_DIR/.env" | tail -1 | cut -d= -f2- | tr -d '"'"'"' ')
    if [ -n "$pg_host" ] && ! getent hosts "$pg_host" >/dev/null 2>&1; then
      pg_override="127.0.0.1"
      info "POSTGRES_HOST=$pg_host doesn't resolve on this host -- dev backend uses 127.0.0.1 instead."
    fi
  fi
  echo "$DB_MODE" > "$DB_MODE_FILE"
  ENVIRONMENT_OVERRIDE="$environment_override" PG_OVERRIDE="$pg_override" python3 -c "
import os, subprocess
env = os.environ.copy()
if env.get('ENVIRONMENT_OVERRIDE'):
    env['ENVIRONMENT'] = env['ENVIRONMENT_OVERRIDE']
elif env.get('ENVIRONMENT', '').strip().lower() == 'test':
    # --prod-db must not inherit a shell's ENVIRONMENT=test: the guard would
    # refuse .env's production target and the backend would never start.
    del env['ENVIRONMENT']
if env.get('PG_OVERRIDE'):
    env['POSTGRES_HOST'] = env['PG_OVERRIDE']
    # Same reason: ForgeRouter is 'forgerouter:2100' on foundation_network, 127.0.0.1:2100 here.
    env.setdefault('FORGEROUTER_URL', 'http://127.0.0.1:2100')
p = subprocess.Popen(
    ['.venv/bin/uvicorn', 'app.main:app', '--reload', '--host', '0.0.0.0', '--port', '$BACKEND_PORT'],
    cwd='$BACKEND_DIR',
    env=env,
    stdout=open('$LOG_DIR/backend.log', 'a'),
    stderr=subprocess.STDOUT,
    start_new_session=True
)
with open('$BACKEND_PID_FILE', 'w') as f:
    f.write(str(p.pid))
"
  wait_for_http "http://localhost:$BACKEND_PORT/health" "backend" "$LOG_DIR/backend.log"
}

start_frontend() {
  local existing
  existing=$(port_owner_pids "$FRONTEND_PORT")
  if [ -n "$existing" ]; then
    if [ -f "$FRONTEND_PID_FILE" ]; then
      ok "Frontend already running on :$FRONTEND_PORT"
      return
    fi
    err "Port $FRONTEND_PORT is already in use (pid(s): $existing) by something dev.sh didn't start -- stop it manually first."
    exit 1
  fi
  info "Starting frontend (vite dev) on :$FRONTEND_PORT ..."
  python3 -c "
import os, subprocess
env = os.environ.copy()
env['VITE_API_URL'] = 'http://localhost:$BACKEND_PORT'
p = subprocess.Popen(
    ['npm', 'run', 'dev', '--', '--port', '$FRONTEND_PORT', '--host'],
    cwd='$FRONTEND_DIR',
    env=env,
    stdout=open('$LOG_DIR/frontend.log', 'a'),
    stderr=subprocess.STDOUT,
    start_new_session=True
)
with open('$FRONTEND_PID_FILE', 'w') as f:
    f.write(str(p.pid))
"
  wait_for_http "http://localhost:$FRONTEND_PORT" "frontend" "$LOG_DIR/frontend.log"
}

wait_for_http() {
  local url="$1" name="$2" log="$3"
  for _ in $(seq 1 60); do
    if curl -sf -o /dev/null "$url"; then
      ok "$name is up: $url"
      return 0
    fi
    sleep 0.5
  done
  err "$name didn't come up in time -- check $log"
  tail -n 20 "$log"
  exit 1
}

cmd_status() {
  local b_pids f_pids
  b_pids=$(port_owner_pids "$BACKEND_PORT" | tr '\n' ' ')
  f_pids=$(port_owner_pids "$FRONTEND_PORT" | tr '\n' ' ')
  if [ -n "$b_pids" ]; then
    ok "Backend up on :$BACKEND_PORT (pid $b_pids) -- database: $(cat "$DB_MODE_FILE" 2>/dev/null || echo unknown)"
  else
    warn "Backend not running"
  fi
  if [ -n "$f_pids" ]; then ok "Frontend up on :$FRONTEND_PORT (pid $f_pids)"; else warn "Frontend not running"; fi
}

cmd_start() {
  check_config
  start_backend
  start_frontend
  echo
  ok "Dev environment ready:"
  echo
  echo "    Frontend  →  http://localhost:$FRONTEND_PORT"
  echo "    Backend   →  http://localhost:$BACKEND_PORT/health"
  if [ "$DB_MODE" = "prod" ]; then
    echo "    Database  →  $(color '1;31' 'PRODUCTION (forgehub_postgres) -- --prod-db')"
  else
    echo "    Database  →  test (forgehub_test @ 127.0.0.1:5439; reset: test-env/reset.sh)"
  fi
  echo
  info "Logs: $LOG_DIR/backend.log, $LOG_DIR/frontend.log"
  info "Stop with: ./dev.sh stop"
  info "Docker deploy (ports 8000/4173) is untouched -- run 'docker compose up -d --build' explicitly to deploy."
}

case "$COMMAND" in
  start)   cmd_start ;;
  stop)    cmd_stop ;;
  restart) cmd_stop; cmd_start ;;
  status)  cmd_status ;;
  *) echo "Usage: $0 [start|stop|restart|status] [--prod-db]"; exit 1 ;;
esac
