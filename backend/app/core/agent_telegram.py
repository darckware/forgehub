"""Per-agent Telegram communication status.

The ecosystem's human channel is Telegram, one bot per Hermes profile
(`ECOSYSTEM_AGENTS.md`'s "Telegram requirements" column, mirrored onto
`Agent.telegram_required`). Until now ForgeHub only showed *whether an agent
is required to have* a Telegram account -- never whether that channel is
actually installed and alive, which is the thing an operator needs at a
glance.

Two independent signals, deliberately kept separate because they fail
independently:

  installed  -- the profile's own `.env` carries a TELEGRAM_BOT_TOKEN and a
                TELEGRAM_HOME_CHANNEL. Read straight off the /profiles mount;
                no secret ever leaves this module (only booleans and the
                channel *name*, never the token).
  running    -- systemd unit `hermes-gateway-<profile>.service` is active.
                That daemon is what long-polls Telegram, so "installed but
                not running" means messages silently go nowhere. The backend
                container has no systemd, so this comes from the host-bridge
                (`/v1/exec`), same as system_control.py's git calls, and is
                reported as None (unknown) rather than False when the bridge
                is unreachable -- "we could not check" must not render as
                "it is broken".

Statuses: ok | not_running | not_configured | unknown | not_applicable.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from app.core.agent_profile_files import resolve_home_dir

# Only these keys are ever read out of the profile .env, and only the
# home-channel *name* is ever returned. TELEGRAM_BOT_TOKEN is reduced to a
# boolean before it leaves this module.
_TOKEN_KEY = "TELEGRAM_BOT_TOKEN"
_CHANNEL_KEY = "TELEGRAM_HOME_CHANNEL"
_CHANNEL_NAME_KEY = "TELEGRAM_HOME_CHANNEL_NAME"

_ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Z0-9_]+)\s*=\s*(.*?)\s*$")

STATUS_OK = "ok"
STATUS_NOT_RUNNING = "not_running"
STATUS_NOT_CONFIGURED = "not_configured"
STATUS_UNKNOWN = "unknown"
STATUS_NOT_APPLICABLE = "not_applicable"


@dataclass
class TelegramStatus:
    profile_slug: str | None
    required: bool
    installed: bool
    home_channel_name: str | None
    service: str | None
    running: bool | None
    status: str


def gateway_service_name(profile_slug: str | None, runtime_type: str | None) -> str | None:
    """The systemd unit that carries this profile's Telegram channel.

    Only Hermes profiles have one. The external CLI runtimes have a
    profile_slug too (it is their inbox addressing key, not a directory under
    /root/.hermes/profiles), so keying off the slug alone wrongly attributed
    a `hermes-gateway-porthos.service` to Porthos and reported that
    non-existent unit as down."""
    if not profile_slug or runtime_type != "hermes":
        return None
    return f"hermes-gateway-{profile_slug}.service"


def _read_env_values(env_path: Path) -> dict[str, str]:
    """Parse only the three TELEGRAM_* keys out of a profile `.env`.

    Hand-rolled rather than python-dotenv because this file is large, mostly
    irrelevant to us, and must never be loaded into the process environment:
    it holds every credential that profile owns."""
    wanted = {_TOKEN_KEY, _CHANNEL_KEY, _CHANNEL_NAME_KEY}
    found: dict[str, str] = {}
    try:
        with env_path.open(encoding="utf-8", errors="replace") as f:
            for line in f:
                if line.lstrip().startswith("#"):
                    continue
                match = _ENV_LINE.match(line)
                if not match:
                    continue
                key, raw = match.group(1), match.group(2)
                if key not in wanted:
                    continue
                value = raw.split(" #", 1)[0].strip().strip("'\"")
                found[key] = value
    except OSError:
        return {}
    return found


def read_profile_telegram_config(
    home_path: str | None, runtime_type: str | None, profile_slug: str | None
) -> tuple[bool, str | None]:
    """(installed, home_channel_name) for one agent.

    `installed` requires both a bot token and a home channel: a token with no
    channel cannot deliver anything, which is exactly the half-configured
    state this check exists to surface."""
    home_dir = resolve_home_dir(home_path)
    if home_dir is None:
        return False, None
    values = _read_env_values(home_dir / ".env")
    installed = bool(values.get(_TOKEN_KEY)) and bool(values.get(_CHANNEL_KEY))
    return installed, values.get(_CHANNEL_NAME_KEY) or None


def parse_active_services(systemctl_stdout: str) -> set[str]:
    """Unit names reported as ActiveState=active by
    `systemctl show --property=Name,ActiveState`-style output.

    Parses the `Name=…`/`ActiveState=…` pairs that `systemctl show` emits per
    unit (blank-line separated). Using `show` rather than `is-active` keeps it
    to a single host-bridge round trip for the whole roster."""
    active: set[str] = set()
    name: str | None = None
    state: str | None = None
    for line in systemctl_stdout.splitlines():
        line = line.strip()
        if not line:
            if name and state == "active":
                active.add(name)
            name, state = None, None
            continue
        if line.startswith("Id="):
            name = line[3:].strip()
        elif line.startswith("ActiveState="):
            state = line[len("ActiveState=") :].strip()
    if name and state == "active":
        active.add(name)
    return active


def resolve_status(
    *,
    required: bool,
    installed: bool,
    service: str | None,
    running: bool | None,
) -> str:
    """Fold the two signals into one badge state.

    `not_applicable` covers the agents Telegram was never part of: no gateway
    service and nothing configured. If an agent *is* configured, it gets a
    real status even when `telegram_required` is false -- a channel that
    exists is a channel that can break."""
    if not installed and service is None:
        return STATUS_NOT_APPLICABLE if not required else STATUS_NOT_CONFIGURED
    if not installed:
        return STATUS_NOT_CONFIGURED
    if running is None:
        return STATUS_UNKNOWN
    return STATUS_OK if running else STATUS_NOT_RUNNING


def build_status(
    *,
    profile_slug: str | None,
    required: bool,
    home_path: str | None,
    runtime_type: str | None,
    active_services: set[str] | None,
) -> TelegramStatus:
    """`active_services=None` means the host-bridge could not be reached, so
    `running` stays None and the status degrades to "unknown" rather than
    falsely reporting the channel as down."""
    installed, channel_name = read_profile_telegram_config(
        home_path, runtime_type, profile_slug
    )
    service = gateway_service_name(profile_slug, runtime_type)
    running: bool | None = None
    if service is not None and active_services is not None:
        running = service in active_services
    return TelegramStatus(
        profile_slug=profile_slug,
        required=required,
        installed=installed,
        home_channel_name=channel_name,
        service=service,
        running=running,
        status=resolve_status(
            required=required, installed=installed, service=service, running=running
        ),
    )
