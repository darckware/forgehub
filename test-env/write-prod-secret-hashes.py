"""Write test-env/.prod-secret-hashes: salted SHA-256 of every secret (16+
characters) in the repo-root .env, never a value (Plano Integrado T.3).

The test backend and tools containers never get the production .env; under
ENVIRONMENT=test, app/core/config.py compares their credentials against these
hashes and refuses to start on a match. Run by test-env/init-env.sh.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "backend"))
from app.core.test_integration_policy import production_secret_hashes_from_env  # noqa: E402

# The repo-root .env by default; a worktree has none, so it may name the
# checkout's own (read only to hash it).
env_file = Path(sys.argv[1]) if len(sys.argv) > 1 else HERE.parent / ".env"
target = HERE / ".prod-secret-hashes"
if not env_file.is_file():
    print("No repo-root .env: test-env/.prod-secret-hashes not written (the test backend will refuse to start).")
    sys.exit(0)
salt, hashes = production_secret_hashes_from_env(env_file)
target.write_text(json.dumps({
    "source": ".env (repo root)",
    "salt": salt,
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "hashes": hashes,
}, indent=2, sort_keys=True) + "\n", encoding="utf-8")
target.chmod(0o600)
print(f"Wrote test-env/.prod-secret-hashes ({len(hashes)} production secret hashes, no values).")
