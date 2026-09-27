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
  running    -- the profile's Telegram adapter is `connected` in the host
                gateway's own state file (`~/.hermes/gateway_state.json`,
                platform key `<profile>:telegram`), and the gateway PID
                recorded there is alive. Read through the host-bridge
                (`/v1/exec`), reported as None (unknown) rather than False
                when the bridge is unreachable -- "we could not check" must
                not render as "it is broken".

Since Hermes' multiplex mode (September 2026) there is ONE gateway process,
the user unit `hermes-gateway.service`, serving every profile; the old
per-profile `hermes-gateway-<profile>.service` units no longer exist. This
module used to check those units, so every agent read "not running" while
its Telegram was fine -- and, worse, a real outage looked the same as the
false one (2026-09-27: Athos/Aegis/Kairos/Lara were `fatal`
telegram_polling_conflict for 16 hours). A running process is not a working
channel either: the adapter can be `fatal` inside a healthy gateway, which
is why the per-profile platform state is the signal, not the unit.

Statuses: ok | not_running | not_configured | unknown | not_applicable.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from app.core.agent_profile_files import effective_home_path, resolve_home_dir

# Only these keys are ever read out of the profile .env, and only the
# home-channel *name* is ever returned. TELEGRAM_BOT_TOKEN is reduced to a
# boolean before it leaves this module.
_TOKEN_KEY = "TELEGRAM_BOT_TOKEN"
_CHANNEL_KEY = "TELEGRAM_HOME_CHANNEL"
_CHANNEL_NAME_KEY = "TELEGRAM_HOME_CHANNEL_NAME"

# Where each runtime keeps its Telegram bot credentials. Hermes profiles use
# <profile>/.env; the external runtimes keep their own home instead -- Vector
# (OpenClaw) at /root/.openclaw/.env (2026-08-13, Marcelo: "o token do Vector
# fica /root/.openclaw/"). Only Vector has one today: Porthus, Aramis and
# Dartan have no Telegram bot at all, which is a normal state and not a gap.
#
# Recorded here so the *account* behind an agent can be discovered from the
# token it already has (Telegram's getMe) rather than typed in by hand --
# hand-typing thirteen usernames would create a second source of truth that
# drifts the day a bot is replaced. The token itself never leaves this module
# (see the boolean reduction above).
EXTERNAL_RUNTIME_ENV_PATHS = {
    "openclaw": "/root/.openclaw/.env",
}

_ENV_LINE = re.compile(r"^\s*(?:export\s+)?([A-Z0-9_]+)\s*=\s*(.*?)\s*$")

# The single host gateway (multiplex) and the state file it keeps.
GATEWAY_UNIT = "hermes-gateway.service"
GATEWAY_STATE_PATH = "/root/.hermes/gateway_state.json"
_ALIVE_MARKER = "__GATEWAY_PID_ALIVE__"

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
    """The systemd unit that carries this profile's Telegram channel: the
    one multiplex host gateway, for every Hermes profile.

    Only Hermes profiles have one. The external CLI runtimes have a
    profile_slug too (it is their inbox addressing key, not a directory under
    /root/.hermes/profiles), so keying off the slug alone wrongly attributed
    a gateway to Porthus and reported it as down."""
    if not profile_slug or runtime_type != "hermes":
        return None
    return GATEWAY_UNIT


def gateway_state_command() -> str:
    """One host-bridge call: the gateway state file, then whether the PID it
    records is still alive (a crashed gateway leaves the file behind)."""
    return (
        f'f={GATEWAY_STATE_PATH}; cat "$f"; printf "\\n{_ALIVE_MARKER}\\n"; '
        "pid=$(grep -oE '\"pid\": *[0-9]+' \"$f\" | head -1 | grep -oE '[0-9]+$'); "
        '[ -n "$pid" ] && kill -0 "$pid" 2>/dev/null && echo yes || echo no'
    )


def parse_telegram_states(stdout: str) -> dict[str, str]:
    """`{profile_slug: telegram adapter state}` from `gateway_state_command`
    output. Empty when the gateway is not alive or not running -- every
    channel is then down, whatever the (stale) file says. The `default`
    profile's own adapter is keyed `telegram`, without a prefix."""
    body, _, alive = stdout.partition(_ALIVE_MARKER)
    if alive.strip() != "yes":
        return {}
    try:
        state = json.loads(body)
    except ValueError:
        return {}
    if state.get("gateway_state") not in ("running", "starting"):
        return {}
    states: dict[str, str] = {}
    for key, platform in (state.get("platforms") or {}).items():
        if not isinstance(platform, dict):
            continue
        if key == "telegram":
            states["default"] = str(platform.get("state"))
        elif key.endswith(":telegram"):
            states[key.split(":", 1)[0]] = str(platform.get("state"))
    return states


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
    home_dir = resolve_home_dir(effective_home_path(home_path, runtime_type, profile_slug))
    if home_dir is None:
        return False, None
    values = _read_env_values(home_dir / ".env")
    installed = bool(values.get(_TOKEN_KEY)) and bool(values.get(_CHANNEL_KEY))
    return installed, values.get(_CHANNEL_NAME_KEY) or None


def read_profile_home_chat(
    home_path: str | None,
    runtime_type: str | None = None,
    profile_slug: str | None = None,
) -> str | None:
    """The chat id an agent's own profile treats as "mine"
    (TELEGRAM_HOME_CHANNEL), or None when it has none.

    Distinct from read_profile_telegram_config above, which returns the
    channel's *display name* for the status UI -- this returns the id you can
    actually send to. Added 2026-08-13 for replies asked for in the body of a
    request ("me responda no telegram") that don't name a conversation: rather
    than inventing a destination, use the one that profile's own gateway
    already delivers its crons to.

    The token in the same file is never read here (see this module's header:
    it is reduced to a boolean before leaving).
    """
    home_dir = resolve_home_dir(effective_home_path(home_path, runtime_type, profile_slug))
    if home_dir is None:
        return None
    return _read_env_values(home_dir / ".env").get(_CHANNEL_KEY) or None


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
    telegram_states: dict[str, str] | None,
) -> TelegramStatus:
    """`telegram_states=None` means the host-bridge could not be reached, so
    `running` stays None and the status degrades to "unknown" rather than
    falsely reporting the channel as down."""
    installed, channel_name = read_profile_telegram_config(
        home_path, runtime_type, profile_slug
    )
    service = gateway_service_name(profile_slug, runtime_type)
    running: bool | None = None
    if service is not None and telegram_states is not None:
        running = telegram_states.get(profile_slug or "") == "connected"
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
