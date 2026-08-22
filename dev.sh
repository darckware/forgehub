#!/usr/bin/env bash
# Dev-mode launcher for ForgeHub: hot-reload backend (uvicorn --reload) +
# frontend (vite dev), on ports separate from the Docker deploy (8000/4173)
# so both can run side by side. Docker only changes when someone explicitly
# runs `docker compose up -d --build` -- this script never touches it.
#
# Usage:
#   ./dev.sh            start (or restart if already running)
#   ./dev.sh stop        stop both dev servers
#   ./dev.sh status       show whether they're up + health
set -uo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BACKEND_DIR="$ROOT_DIR/backend"
FRONTEND_DIR="$ROOT_DIR/frontend"
STATE_DIR="$ROOT_DIR/.dev"
LOG_DIR="$STATE_DIR/logs"
BACKEND_PID_FILE="$STATE_DIR/backend.pid"
FRONTEND_PID_FILE="$STATE_DIR/frontend.pid"

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

check_config() {
  local failed=0

  if [ ! -f "$ROOT_DIR/.env" ]; then
    err ".env not found at repo root -- copy .env.example and fill in Postgres credentials first."
    failed=1
  fi

  if [ ! -x "$BACKEND_DIR/.venv/bin/uvicorn" ]; then
    warn "backend/.venv missing or incomplete -- creating it and installing requirements.txt (first run only, takes a bit)."
    python3 -m venv "$BACKEND_DIR/.venv" || { err "Failed to create backend venv"; failed=1; }
    "$BACKEND_DIR/.venv/bin/pip" install -q -r "$BACKEND_DIR/requirements.txt" || { err "pip install failed"; failed=1; }
  fi

  if [ ! -x "$FRONTEND_DIR/node_modules/.bin/vite" ]; then
    warn "frontend/node_modules missing or incomplete -- running npm install (first run only, takes a bit)."
    (cd "$FRONTEND_DIR" && npm install --silent) || { err "npm install failed"; failed=1; }
  fi

  if [ "$failed" -ne 0 ]; then
    err "Config checks failed -- fix the above before starting."
    exit 1
  fi
  ok "Config checks passed (.env, backend venv, frontend deps)"
}

start_backend() {
  local existing
  existing=$(port_owner_pids "$BACKEND_PORT")
  if [ -n "$existing" ]; then
    if [ -f "$BACKEND_PID_FILE" ]; then
      ok "Backend already running on :$BACKEND_PORT"
      return
    fi
    err "Port $BACKEND_PORT is already in use (pid(s): $existing) by something dev.sh didn't start -- stop it manually first."
    exit 1
  fi
  info "Starting backend (uvicorn --reload) on :$BACKEND_PORT ..."
  python3 -c "
import subprocess
p = subprocess.Popen(
    ['.venv/bin/uvicorn', 'app.main:app', '--reload', '--host', '0.0.0.0', '--port', '$BACKEND_PORT'],
    cwd='$BACKEND_DIR',
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
  if [ -n "$b_pids" ]; then ok "Backend up on :$BACKEND_PORT (pid $b_pids)"; else warn "Backend not running"; fi
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
  echo
  info "Logs: $LOG_DIR/backend.log, $LOG_DIR/frontend.log"
  info "Stop with: ./dev.sh stop"
  info "Docker deploy (ports 8000/4173) is untouched -- run 'docker compose up -d --build' explicitly to deploy."
}

case "${1:-start}" in
  start)   cmd_start ;;
  stop)    cmd_stop ;;
  restart) cmd_stop; cmd_start ;;
  status)  cmd_status ;;
  *) echo "Usage: $0 [start|stop|restart|status]"; exit 1 ;;
esac
