#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")/.."

./scripts/build.sh
./scripts/compose-vault.py up -d --no-build
