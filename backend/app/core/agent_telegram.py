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

import httpx

from app.core.agent_profile_files import effective_home_path, resolve_home_dir
from app.core.config import settings

# Only these keys are ever read out of the profile .env, and only the
# home-channel *name* is ever returned. TELEGRAM_BOT_TOKEN is reduced to a
# boolean before it leaves this module.
_TOKEN_KEY = "TELEGRAM_BOT_TOKEN"
_CHANNEL_KEY = "TELEGRAM_HOME_CHANNEL"
_CHANNEL_NAME_KEY = "TELEGRAM_HOME_CHANNEL_NAME"

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


def parse_gateway_state(stdout: str) -> tuple[bool, dict[str, str]]:
    """(gateway alive, `{profile_slug: telegram adapter state}`) from
    `gateway_state_command` output.

    Alive means the PID the state file records is running and the gateway
    reports itself `running`/`starting`; otherwise every channel is down,
    whatever the (stale) file says, and the states are empty. The `default`
    profile's own adapter is keyed `telegram`, without a prefix."""
    body, _, alive = stdout.partition(_ALIVE_MARKER)
    if alive.strip() != "yes":
        return False, {}
    try:
        state = json.loads(body)
    except ValueError:
        return False, {}
    if not isinstance(state, dict) or state.get("gateway_state") not in ("running", "starting"):
        return False, {}
    states: dict[str, str] = {}
    for key, platform in (state.get("platforms") or {}).items():
        if not isinstance(platform, dict):
            continue
        if key == "telegram":
            states["default"] = str(platform.get("state"))
        elif key.endswith(":telegram"):
            states[key.split(":", 1)[0]] = str(platform.get("state"))
    return True, states


def parse_telegram_states(stdout: str) -> dict[str, str]:
    """`{profile_slug: telegram adapter state}`; empty when the gateway is
    not alive (see `parse_gateway_state`)."""
    return parse_gateway_state(stdout)[1]


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

    `not_applicable` covers the agents Telegram is not part of: nothing
    configured and not required -- including Hermes profiles served by the
    gateway whose Telegram was deliberately dropped (2026-09-27: Atlas,
    Daedalus, Hephaestus, Mnemosyne, Scriba, Themis are reached through
    Messages). If an agent *is* configured, it gets a real status even when
    `telegram_required` is false -- a channel that exists is a channel that
    can break."""
    if not installed:
        return STATUS_NOT_CONFIGURED if required else STATUS_NOT_APPLICABLE
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


@dataclass
class GatewayHealth:
    """One read of the multiplex host gateway. `alive`/`telegram_states` are
    None when the host-bridge could not be read (`error` says why): unknown,
    never "down"."""

    alive: bool | None
    telegram_states: dict[str, str] | None
    error: str | None


async def read_gateway_health() -> GatewayHealth:
    """The host gateway's liveness and each Hermes profile's Telegram adapter
    state, read from the gateway's own state file through the host-bridge
    (`/v1/exec` -- the backend container sees neither the host's systemd nor
    ~/.hermes). Never raises."""
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                f"{settings.CHAT_BRIDGE_URL}/v1/exec",
                headers={"X-Bridge-Token": settings.CHAT_BRIDGE_TOKEN},
                json={"command": gateway_state_command()},
            )
    except httpx.HTTPError as e:
        return GatewayHealth(None, None, f"Host-bridge unreachable: {e}")
    if resp.status_code != 200:
        return GatewayHealth(None, None, f"Host-bridge error: {resp.text[:200]}")
    try:
        stdout = resp.json().get("stdout") or ""
    except ValueError:
        return GatewayHealth(None, None, "Host-bridge returned a non-JSON body")
    alive, states = parse_gateway_state(stdout)
    return GatewayHealth(alive, states, None)


async def read_telegram_platform_states() -> tuple[dict[str, str] | None, str | None]:
    """Each Hermes profile's Telegram adapter state (see `read_gateway_health`).

    Returns (None, error) rather than raising: a Telegram badge that cannot
    be computed must degrade to "unknown", never take down the page asking."""
    health = await read_gateway_health()
    return health.telegram_states, health.error


GATEWAY_OK = "ok"
GATEWAY_DOWN = "down"


@dataclass
class ChannelHealth:
    """Board badge for one agent: its Telegram channel and the gateway that
    carries it. `gateway` is `not_applicable` for agents the gateway doesn't
    serve (external runtimes, agents without a profile)."""

    telegram: str
    gateway: str


def build_channel_health(
    *,
    profile_slug: str | None,
    required: bool,
    home_path: str | None,
    runtime_type: str | None,
    gateway: GatewayHealth | None,
) -> ChannelHealth:
    """`gateway=None` (or a failed read) folds to `unknown`, never a failure."""
    telegram = build_status(
        profile_slug=profile_slug,
        required=required,
        home_path=home_path,
        runtime_type=runtime_type,
        telegram_states=gateway.telegram_states if gateway is not None else None,
    ).status
    if gateway_service_name(profile_slug, runtime_type) is None:
        gateway_status = STATUS_NOT_APPLICABLE
    elif gateway is None or gateway.alive is None:
        gateway_status = STATUS_UNKNOWN
    else:
        gateway_status = GATEWAY_OK if gateway.alive else GATEWAY_DOWN
    return ChannelHealth(telegram=telegram, gateway=gateway_status)
