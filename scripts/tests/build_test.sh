#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
test_dir="$(mktemp -d)"
trap 'rm -rf "$test_dir"' EXIT

cat >"$test_dir/docker" <<'EOF'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >>"${FORGEHUB_DOCKER_CALLS}"

if [[ "$*" == "compose images -q forgehub-backend" ]]; then
  printf '%s\n' 'sha256:stale-backend'
elif [[ "$*" == "compose images -q forgehub-frontend" ]]; then
  printf '%s\n' 'sha256:stale-frontend'
elif [[ "$*" == "tag sha256:stale-backend"* || "$*" == "tag sha256:stale-frontend"* ]]; then
  printf '%s\n' 'No such image' >&2
  exit 1
fi
EOF
chmod +x "$test_dir/docker"

export FORGEHUB_DOCKER_CALLS="$test_dir/docker-calls"
PATH="$test_dir:$PATH" "$repo_root/scripts/build.sh"

grep -Fxq 'compose build' "$FORGEHUB_DOCKER_CALLS"
grep -Fxq 'tag forgehub-backend:latest forgehub-backend:0.1.0' "$FORGEHUB_DOCKER_CALLS"
grep -Fxq 'tag forgehub-frontend:latest forgehub-frontend:0.1.0' "$FORGEHUB_DOCKER_CALLS"

if grep -Fq 'compose images -q' "$FORGEHUB_DOCKER_CALLS"; then
  printf '%s\n' 'build.sh must not resolve new images from running containers' >&2
  exit 1
fi
