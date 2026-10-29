#!/usr/bin/env bash
# Create test-env/.env.test from the versioned template, with a freshly
# generated random password. Never overwrites an existing file: the volume
# was initialized with that password, and a new one would lock it out.
set -euo pipefail

DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET="$DIR/.env.test"

if [ -f "$TARGET" ]; then
  echo "test-env/.env.test already exists -- left untouched."
  exit 0
fi

umask 077
password="$(python3 -c 'import secrets; print(secrets.token_hex(24))')"
sed "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=$password/" "$DIR/.env.test.example" > "$TARGET"
echo "Created test-env/.env.test (mode 600) with a random password."
