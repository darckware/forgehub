#!/usr/bin/env bash
# Create or complete test-env/.env.test, then refresh the production-secret
# hashes the test containers compare against (Plano Integrado T.1/T.3).
#
# - Missing file: created from .env.test.example with a random database
#   password.
# - Existing file: a value already set is never changed -- the volume was
#   initialized with that password, and a new one would lock it out. Only
#   keys the template has and the file lacks are added, and only `change-me`
#   placeholders are replaced with random values.
# - test-env/.prod-secret-hashes: SHA-256 of every secret in the repo-root
#   .env (no value is written or printed). The test containers never get the
#   .env, so this is how their backend proves its credentials are not
#   production ones. Refreshed on every run.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="$DIR/.env.test"

umask 077
python3 - "$DIR/.env.test.example" "$TARGET" <<'PY'
import re, secrets, sys
from pathlib import Path

template, target = Path(sys.argv[1]), Path(sys.argv[2])
created = not target.exists()
lines = (template if created else target).read_text(encoding="utf-8").splitlines()
present = {m.group(1) for line in lines if (m := re.match(r"\s*([A-Z0-9_]+)=", line))}
for line in template.read_text(encoding="utf-8").splitlines():
    m = re.match(r"\s*([A-Z0-9_]+)=", line)
    if m and m.group(1) not in present:
        lines.append(line)
        present.add(m.group(1))
filled = []
out = []
for line in lines:
    m = re.match(r"\s*([A-Z0-9_]+)=(.*)$", line)
    if m and m.group(2).strip() == "change-me":
        size = 24 if m.group(1) == "POSTGRES_PASSWORD" else 32
        line = f"{m.group(1)}={secrets.token_hex(size)}"
        filled.append(m.group(1))
    out.append(line)
target.write_text("\n".join(out) + "\n", encoding="utf-8")
target.chmod(0o600)
verb = "Created" if created else "Updated"
print(f"{verb} test-env/.env.test (mode 600); generated: {', '.join(filled) or 'nothing'}.")
PY

# Optional argument: the production .env to hash (a worktree has none of its own).
python3 "$DIR/write-prod-secret-hashes.py" "$@"
