"""What a test process may reach and with which credentials (Plano Integrado T.3, 2026-10-29).

ENVIRONMENT=test already refuses any database off the test allowlist (T.1) and
starts no background loop (T.2). This module closes the other two ways a test
process could touch the real world:

- **Integrations.** Every external integration has exactly one switch point: its
  base URL in `Settings`. Under test each one must be empty (the call fails with
  the integration's own "not configured / unreachable" error) or point at the
  local integration stub (`app/tests/fixtures/integration_stub.py`, container
  `forgehub_test_stubs`), under that integration's own path prefix. Anything
  else -- the real host-bridge, Darckware, ForgeRouter, Tailscale, a client's
  host, an address nobody listed -- refuses the whole process at start-up. No
  route knows the stub exists: it only ever sees a URL.
- **Credentials.** JWT_SECRET, CHAT_BRIDGE_TOKEN, the credential-encryption key
  and the activity-webhook secret must be the test's own: set, not the code
  default, distinct from each other, and not equal to any secret of the
  production `.env`. The comparison is by SHA-256 only; no value is ever kept,
  logged or put in an error message.

Pure functions, no I/O except reading the production reference (the repo-root
`.env`, or the hash file test-env/init-env.sh writes for containers that don't
have it). Imported by app/core/config.py, which must not be imported here.
"""
from __future__ import annotations

import hashlib
import json
import re
import secrets
from pathlib import Path
from urllib.parse import urlsplit


class UnsafeTestConfigurationError(RuntimeError):
    """A test process was configured to reach a real integration or to use a
    production (or default) credential. A RuntimeError, like
    UnsafeDatabaseTargetError, so pydantic lets it propagate as-is."""


# --- Integrations ------------------------------------------------------------

#: Where the stub answers: by container name inside forgehub_test_network (the
#: test backend/tools containers), and through forgehub_test_gateway from the
#: host (dev.sh's backend, pytest on the host).
STUB_ORIGINS: frozenset[tuple[str, str, int]] = frozenset({
    ("http", "forgehub_test_stubs", 8900),
    ("http", "127.0.0.1", 8003),
    ("http", "localhost", 8003),
})

#: Setting name -> (integration label, path prefix the stub serves it under).
#: The host-bridge is served at the root because its callers append `/v1/...`
#: themselves; every other integration gets its own prefix so the stub can
#: tell them apart and a URL meant for one can't silently reach another.
INTEGRATION_URL_SETTINGS: dict[str, tuple[str, str]] = {
    "CHAT_BRIDGE_URL": ("host-bridge", ""),
    "DARCKWARE_API_URL": ("darckware", "/darckware"),
    "FORGEROUTER_URL": ("forgerouter", "/forgerouter"),
    "TAILSCALE_API_URL": ("tailscale", "/tailscale"),
    "WEATHER_API_URL": ("weather", "/weather"),
    "WEATHER_REVERSE_GEOCODE_URL": ("weather", "/weather"),
}

#: Hosts known to be production or a client's, named in the refusal so it says
#: *why*. The allowlist above is what decides; this only explains.
PRODUCTION_INTEGRATION_HOSTS = frozenset({
    "host.docker.internal", "forgehub-backend", "forgehub_postgres", "darckware-backend",
    "forgerouter", "forgevault", "hindsight", "api.telegram.org", "api.tailscale.com",
    "login.tailscale.com", "www.google.com", "api.open-meteo.com", "nominatim.openstreetmap.org",
})
PRODUCTION_INTEGRATION_PORTS = frozenset({8910, 8000, 8020, 2100})
_PRODUCTION_DOMAINS = (".darckware.net", "darckware.net", ".darckware.com.br")


def _describe(url: str) -> str:
    """Scheme://host:port of a URL, never its path, query or userinfo (which
    could carry a token)."""
    parts = urlsplit(url)
    host = parts.hostname or "?"
    return f"{parts.scheme or '?'}://{host}" + (f":{parts.port}" if parts.port else "")


def integration_url_problem(name: str, url: str | None) -> str | None:
    """Why `url` is not acceptable for setting `name` under test, or None.

    Empty is acceptable (the integration is off and its caller fails with its
    own error); otherwise only a stub origin with the integration's prefix."""
    value = (url or "").strip()
    if not value:
        return None
    label, prefix = INTEGRATION_URL_SETTINGS[name]
    try:
        parts = urlsplit(value)
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError:
        return f"{name} is not a valid URL"
    host = (parts.hostname or "").lower()
    if parts.username or parts.password:
        return f"{name} carries credentials in the URL"
    if (parts.scheme, host, port) in STUB_ORIGINS:
        path = parts.path.rstrip("/")
        if path != prefix:
            return f"{name} ({label}) must use the stub path {prefix or '/'!r}, not {parts.path or '/'!r}"
        return None
    reasons = []
    if host in PRODUCTION_INTEGRATION_HOSTS or host.endswith(_PRODUCTION_DOMAINS) or host in _PRODUCTION_DOMAINS:
        reasons.append(f"host {host!r} is production")
    if port in PRODUCTION_INTEGRATION_PORTS:
        reasons.append(f"port {port} is a production service")
    reasons.append("not the integration stub (http://forgehub_test_stubs:8900 or http://127.0.0.1:8003)")
    return f"{name} ({label}) -> {_describe(value)}: " + "; ".join(reasons)


# --- Fictitious targets (hosts a test may name, e.g. a machine to run a script on)

_FICTITIOUS_NETWORKS = ("192.0.2.", "198.51.100.", "203.0.113.")  # RFC 5737 TEST-NET-1/2/3


def is_fictitious_host(host: str | None) -> bool:
    """RFC 5737 documentation addresses and `.test` names (RFC 2606) only --
    the seed's machines. A real client's LAN address, a tailnet 100.x, a
    public name: all refused."""
    value = (host or "").strip().lower().rstrip(".")
    if not value:
        return False
    if "@" in value:  # user@host
        value = value.rsplit("@", 1)[1]
    if value.count(":") == 1:  # host:port (IPv6 is never fictitious here)
        value = value.split(":", 1)[0]
    if re.fullmatch(r"\d{1,3}(\.\d{1,3}){3}", value):
        return value.startswith(_FICTITIOUS_NETWORKS)
    return value == "test" or value.endswith(".test")


# --- Credentials ---------------------------------------------------------------

#: Test-only credentials and the value each one has when nobody set it.
REQUIRED_TEST_SECRETS: dict[str, str] = {
    "JWT_SECRET": "dev_only_insecure_jwt_secret_change_me",
    "CHAT_BRIDGE_TOKEN": "",
    "SECRETS_ENCRYPTION_KEY": "",
    "AGENT_ACTIVITY_WEBHOOK_SECRET": "",
}
#: Optional under test, but when set they must not be a production value.
OPTIONAL_TEST_SECRETS = (
    "DARCKWARE_AGENT_TOKEN", "DARCKWARE_APPROVER_TOKEN", "FORGEROUTER_SSO_SECRET", "POSTGRES_PASSWORD",
)
MIN_TEST_SECRET_LENGTH = 32

#: A key of the production .env is a secret when its name says so.
_SECRET_KEY_NAME = re.compile(r"(SECRET|TOKEN|PASSWORD|_KEY$|^KEY$|API_KEY)", re.IGNORECASE)
#: Shorter production values are left out of the reference: a test credential
#: is at least MIN_TEST_SECRET_LENGTH long, so it can never equal one, and a
#: short (human) password is the only kind a hash could leak by guessing.
MIN_REFERENCE_SECRET_LENGTH = 16

#: [(salt, {production key: sha256(salt + value)})]. Salted so the hash file
#: can't be matched against a precomputed table.
ProductionReference = list[tuple[str, dict[str, str]]]


def secret_hash(value: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{value}".encode("utf-8")).hexdigest()


def _parse_env_file(path: Path) -> dict[str, str]:
    """KEY=VALUE lines the way python-dotenv reads the common cases (comments,
    `export `, surrounding quotes). Used only to hash; values never leave."""
    try:
        from dotenv import dotenv_values  # python-dotenv, a pydantic-settings dependency
    except ImportError:  # pragma: no cover -- system python3 in init-env.sh
        dotenv_values = None
    if dotenv_values is not None:
        return {k: v for k, v in dotenv_values(path).items() if v is not None}
    values: dict[str, str] = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[len("export "):]
        key, _, value = line.partition("=")
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "'\"":
            value = value[1:-1]
        values[key.strip()] = value
    return values


def production_secret_hashes_from_env(path: Path, salt: str | None = None) -> tuple[str, dict[str, str]]:
    """(salt, {key: hash}) of every long-enough secret in a production .env."""
    salt = salt or secrets.token_hex(16)
    return salt, {
        key: secret_hash(value, salt)
        for key, value in _parse_env_file(path).items()
        if len(value or "") >= MIN_REFERENCE_SECRET_LENGTH and _SECRET_KEY_NAME.search(key)
    }


def load_production_secret_hashes(env_file: Path, hash_file: Path) -> ProductionReference | None:
    """The production reference: the repo-root .env when this process can see
    it (host), plus the hash file init-env.sh writes (containers, which never
    get the .env). None when neither exists -- the caller refuses then, since
    "nothing to compare against" can't prove a credential is test-only."""
    reference: ProductionReference = []
    found = False
    if hash_file.is_file():
        found = True
        data = json.loads(hash_file.read_text(encoding="utf-8"))
        reference.append((str(data["salt"]), {str(k): str(v) for k, v in (data.get("hashes") or {}).items()}))
    if env_file.is_file():
        found = True
        reference.append(production_secret_hashes_from_env(env_file))
    return reference if found else None


def _production_match(value: str, reference: ProductionReference) -> list[str]:
    """Production keys whose value equals `value` (by salted hash)."""
    matches: set[str] = set()
    for salt, hashes in reference:
        digest = secret_hash(value, salt)
        matches.update(key for key, h in hashes.items() if h == digest)
    return sorted(matches)


def credential_problems(values: dict[str, str], reference: ProductionReference | None) -> list[str]:
    """Every reason the test credentials are unsafe. Messages name settings,
    never values."""
    problems: list[str] = []
    if reference is None:
        problems.append(
            "no production reference to compare the test credentials against "
            "(repo-root .env or test-env/.prod-secret-hashes) -- run test-env/init-env.sh"
        )
        reference = []
    seen: dict[str, str] = {}
    for name, default in REQUIRED_TEST_SECRETS.items():
        value = values.get(name) or ""
        if not value or value == default or value == "change-me":
            problems.append(f"{name} is unset or the code default -- test-env/init-env.sh generates a test value")
            continue
        if len(value) < MIN_TEST_SECRET_LENGTH:
            problems.append(f"{name} is shorter than {MIN_TEST_SECRET_LENGTH} characters")
        if matched := _production_match(value, reference):
            problems.append(f"{name} is equal to a production secret ({', '.join(matched)}, matched by SHA-256)")
        if value in seen:
            problems.append(f"{name} is equal to {seen[value]}; each test credential needs its own value")
        seen[value] = name
    for name in OPTIONAL_TEST_SECRETS:
        value = values.get(name) or ""
        if value and (matched := _production_match(value, reference)):
            problems.append(f"{name} is equal to a production secret ({', '.join(matched)}, matched by SHA-256)")
    return problems


def assert_safe_test_configuration(
    integration_urls: dict[str, str | None],
    credentials: dict[str, str],
    production_reference: ProductionReference | None,
    *,
    extra_problems: list[str] | None = None,
) -> None:
    problems = [p for name, url in integration_urls.items() if (p := integration_url_problem(name, url))]
    problems += credential_problems(credentials, production_reference)
    problems += extra_problems or []
    if problems:
        raise UnsafeTestConfigurationError(
            "ENVIRONMENT=test refuses to start: " + " | ".join(problems)
        )
