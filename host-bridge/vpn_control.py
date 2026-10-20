"""Tailscale read model and fixed operations for ForgeHub's Remote Access page.

The bridge runs on the VPS itself, so the tailnet is read from *this* node's
point of view: ``self`` is the VPS and ``peers`` is every device it can reach
(client workstations, servers, admin devices). Until 2026-10-15 this module
assumed a laptop (``NotebookSTI-wsl``) talking to the VPS as a fixed pair and
cut ``tailscale status --json`` at 8 KB -- with ten devices the JSON is ~17 KB,
so every read failed as ``invalid_response`` and the page showed both ends as
unavailable.

Callers never pass a command line. They pick ``self`` or a peer's stable
Tailscale ID plus an action from a fixed set; a peer's address is always taken
from a fresh status read, never from the request.
"""

from __future__ import annotations

import ipaddress
import json
import re
import subprocess
from datetime import datetime, timezone
from typing import Any, Callable


TAILSCALE_NETWORK = ipaddress.ip_network("100.64.0.0/10")
# The status JSON grows with every device; this is a sanity cap, not a size
# the payload is expected to approach.
MAX_STATUS_BYTES = 2 * 1024 * 1024
SELF_NODE = "self"
SELF_ACTIONS = frozenset({"restart"})
PEER_ACTIONS = frozenset({"test"})
_PEER_ID_RE = re.compile(r"^[A-Za-z0-9]{1,64}$")
_ZERO_TIME_PREFIX = "0001-01-01"


class VpnPolicyError(ValueError):
    pass


def _tailscale_ipv4(addresses: object) -> str | None:
    if not isinstance(addresses, list):
        return None
    for value in addresses:
        try:
            address = ipaddress.ip_address(value)
        except ValueError:
            continue
        if address.version == 4 and address in TAILSCALE_NETWORK:
            return str(address)
    return None


def _subnet_routes(data: dict[str, Any]) -> list[str]:
    """Subnets this peer routes for us: its approved routes as this node sees
    them (``PrimaryRoutes`` plus the non-host ``AllowedIPs``). The tailnet only
    hands a node the routes its ACL lets it reach, so an empty list means "no
    usable route from here", not "advertises nothing" -- that needs the
    Tailscale API. Exit-node defaults are not subnets and are left out."""
    candidates: list[object] = []
    for key in ("PrimaryRoutes", "AllowedIPs"):
        value = data.get(key)
        if isinstance(value, list):
            candidates.extend(value)
    routes: set[ipaddress.IPv4Network | ipaddress.IPv6Network] = set()
    for value in candidates:
        try:
            network = ipaddress.ip_network(value, strict=False)
        except (TypeError, ValueError):
            continue
        if network.prefixlen == 0 or network.prefixlen == network.max_prefixlen:
            continue
        if network.version == 4 and network.subnet_of(TAILSCALE_NETWORK):
            continue
        routes.add(network)
    return [str(net) for net in sorted(routes, key=lambda net: (net.version, net))][:50]


def _str(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


def _int(value: object) -> int:
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def _timestamp(value: object) -> str | None:
    # Tailscale reports "0001-01-01T00:00:00Z" for "never"/"now" -- not a date.
    text = _str(value)
    return None if text is None or text.startswith(_ZERO_TIME_PREFIX) else text


def _machine_name(data: dict[str, Any]) -> str | None:
    # DNSName ("gat-adm-pc01.tailxxxx.ts.net.") is the name the admin console
    # and `tailscale status` show; HostName is whatever the OS calls itself.
    dns_name = _str(data.get("DNSName"))
    if dns_name:
        label = dns_name.split(".", 1)[0]
        if label:
            return label
    return _str(data.get("HostName"))


def _tags(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [tag for tag in value if isinstance(tag, str) and tag][:20]


def _connection(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("Online") is not True:
        return {"kind": "unavailable", "relay": None}
    if _str(data.get("CurAddr")):
        return {"kind": "direct", "relay": None}
    if _str(data.get("Relay")) and data.get("Active") is True:
        return {"kind": "derp", "relay": str(data["Relay"])}
    return {"kind": "idle", "relay": None}


def _node_common(data: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": _machine_name(data),
        "hostname": _str(data.get("HostName")),
        "dns_name": (_str(data.get("DNSName")) or "").rstrip(".") or None,
        "os": _str(data.get("OS")),
        "tags": _tags(data.get("Tags")),
        "tailscale_ipv4": _tailscale_ipv4(data.get("TailscaleIPs")),
        "subnet_routes": _subnet_routes(data),
        "rx_bytes": _int(data.get("RxBytes")),
        "tx_bytes": _int(data.get("TxBytes")),
        "key_expiry": _timestamp(data.get("KeyExpiry")),
    }


def _self_node(data: object, backend_state: str) -> dict[str, Any]:
    raw = data if isinstance(data, dict) else {}
    if backend_state == "NeedsLogin":
        state = "needs_login"
    elif not raw:
        state = "unavailable"
    else:
        state = "online" if backend_state == "Running" else "offline"
    return {"id": SELF_NODE, **_node_common(raw), "state": state, "online": state == "online"}


def _peer_node(data: dict[str, Any]) -> dict[str, Any] | None:
    peer_id = _str(data.get("ID"))
    if peer_id is None or not _PEER_ID_RE.fullmatch(peer_id):
        return None
    online = data.get("Online") is True
    return {
        "id": peer_id,
        **_node_common(data),
        "state": "online" if online else "offline",
        "online": online,
        "active": data.get("Active") is True,
        "last_seen": _timestamp(data.get("LastSeen")),
        "connection": _connection(data),
    }


def parse_status(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("invalid_response") from exc
    if not isinstance(payload, dict):
        raise ValueError("invalid_response")

    backend_state = str(payload.get("BackendState") or "Unknown")
    peers: list[dict[str, Any]] = []
    raw_peers = payload.get("Peer")
    if isinstance(raw_peers, dict):
        for candidate in raw_peers.values():
            if isinstance(candidate, dict):
                node = _peer_node(candidate)
                if node is not None:
                    peers.append(node)
    peers.sort(key=lambda node: (not node["online"], (node["name"] or "").lower()))
    return {
        "backend_state": backend_state,
        "self": _self_node(payload.get("Self"), backend_state),
        "peers": peers,
    }


def parse_ping(raw: str) -> dict[str, Any]:
    latency = re.search(r"\bin\s+([0-9]+(?:\.[0-9]+)?)ms\b", raw)
    derp = re.search(r"\bDERP\(([a-z0-9-]+)\)", raw, re.IGNORECASE)
    direct = re.search(r"\bvia\s+(?!DERP\()[^\s]+\s+in\s+", raw, re.IGNORECASE)
    if not latency or (not derp and not direct):
        return {"success": False, "kind": "unavailable", "relay": None, "latency_ms": None}
    return {
        "success": True,
        "kind": "derp" if derp else "direct",
        "relay": derp.group(1).lower() if derp else None,
        "latency_ms": float(latency.group(1)),
    }


def parse_prefs(raw: str) -> dict[str, bool]:
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("invalid_response") from exc
    if not isinstance(payload, dict):
        raise ValueError("invalid_response")
    advertise_routes = payload.get("AdvertiseRoutes")
    advertises_exit = isinstance(advertise_routes, list) and any(
        route in {"0.0.0.0/0", "::/0"} for route in advertise_routes
    )
    posture = {
        "accept_dns": payload.get("CorpDNS") is True,
        "accept_routes": payload.get("RouteAll") is True,
        "advertise_exit_node": advertises_exit,
        "tailscale_ssh": payload.get("RunSSH") is True,
        "exit_node": bool(payload.get("ExitNodeID")),
    }
    return {**posture, "restricted": not any(posture.values())}


def _default_runner(argv: list[str], timeout: float):
    return subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)


def _unavailable(code: str, summary: str, checked_at: str) -> dict[str, Any]:
    return {
        "backend_state": "Unavailable",
        "self": _self_node({}, "Unavailable"),
        "peers": [],
        "sources": [{"name": "status", "status": "unavailable", "checked_at": checked_at, "error_code": code}],
        "error": {"code": code, "summary": summary},
    }


class VpnControl:
    def __init__(self, runner: Callable[..., Any] = _default_runner) -> None:
        self.runner = runner

    def status(self) -> dict[str, Any]:
        checked_at = datetime.now(timezone.utc).isoformat()
        try:
            result = self.runner(["tailscale", "status", "--json"], 10.0)
        except FileNotFoundError:
            return _unavailable("binary_missing", "VPN status executable is unavailable.", checked_at)
        except subprocess.TimeoutExpired:
            return _unavailable("timeout", "VPN status check timed out.", checked_at)
        if result.returncode != 0:
            return _unavailable("daemon_unavailable", "Tailscale status is unavailable.", checked_at)
        stdout = result.stdout or ""
        if len(stdout) > MAX_STATUS_BYTES:
            return _unavailable("invalid_response", "VPN status returned too much data.", checked_at)
        try:
            status = parse_status(stdout)
        except ValueError:
            return _unavailable("invalid_response", "VPN status returned invalid data.", checked_at)

        sources = [{"name": "status", "status": "fresh", "checked_at": checked_at, "error_code": None}]
        try:
            daemon = self.runner(["systemctl", "is-active", "tailscaled"], 5.0)
            daemon_state = daemon.stdout.strip()[:30] or ("active" if daemon.returncode == 0 else "inactive")
            sources.append({"name": "systemd", "status": "fresh", "checked_at": checked_at, "error_code": None})
        except (FileNotFoundError, subprocess.TimeoutExpired):
            daemon_state = "unavailable"
            sources.append({"name": "systemd", "status": "unavailable", "checked_at": checked_at, "error_code": "probe_failed"})

        try:
            prefs = self.runner(["tailscale", "debug", "prefs"], 5.0)
            if prefs.returncode != 0:
                raise ValueError("invalid_response")
            posture = parse_prefs((prefs.stdout or "")[:65536])
            sources.append({"name": "preferences", "status": "fresh", "checked_at": checked_at, "error_code": None})
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
            posture = None
            sources.append({"name": "preferences", "status": "unavailable", "checked_at": checked_at, "error_code": "probe_failed"})

        status["self"]["daemon_state"] = daemon_state
        status["self"]["posture"] = posture
        status["sources"] = sources
        return status

    def action(self, node: str, action: str) -> dict[str, Any]:
        if node == SELF_NODE:
            if action not in SELF_ACTIONS:
                raise VpnPolicyError("action_not_allowed")
            return self._restart_self()
        if not _PEER_ID_RE.fullmatch(node) or action not in PEER_ACTIONS:
            raise VpnPolicyError("action_not_allowed")
        return self._test_peer(node)

    def _run(self, argv: list[str], timeout: float) -> tuple[Any | None, dict[str, Any] | None]:
        try:
            return self.runner(argv, timeout), None
        except FileNotFoundError:
            return None, {"success": False, "code": "binary_missing", "summary": "VPN operation executable is unavailable."}
        except subprocess.TimeoutExpired:
            return None, {"success": False, "code": "timeout", "summary": "VPN operation timed out."}

    def _restart_self(self) -> dict[str, Any]:
        result, error = self._run(["systemctl", "restart", "tailscaled"], 30.0)
        if error:
            return error
        if result.returncode != 0:
            return _failure(result)
        if self.status()["self"]["state"] != "online":
            return {"success": False, "code": "not_online", "summary": "Tailscale did not return online on this server."}
        return {"success": True, "code": "ok", "summary": "Tailscale restarted on this server."}

    def _test_peer(self, peer_id: str) -> dict[str, Any]:
        status = self.status()
        peer = next((item for item in status.get("peers", []) if item["id"] == peer_id), None)
        if peer is None:
            return {"success": False, "code": "peer_not_found", "summary": "Device is not in the tailnet."}
        label = peer.get("name") or peer_id
        if not peer["online"] or not peer.get("tailscale_ipv4"):
            return {"success": False, "code": "peer_offline", "summary": f"{label} is offline.", "target_name": label}
        argv = ["tailscale", "ping", "--until-direct=false", "--c", "1", "--timeout", "5s", peer["tailscale_ipv4"]]
        result, error = self._run(argv, 15.0)
        if error:
            return {**error, "target_name": label}
        if result.returncode != 0:
            return {**_failure(result), "target_name": label}
        ping = parse_ping((result.stdout or "")[:8192])
        if not ping["success"]:
            return {"success": False, "code": "no_reply", "summary": f"{label} did not answer.", "target_name": label}
        path = f"DERP {ping['relay']}" if ping["kind"] == "derp" else "direct"
        return {
            "success": True,
            "code": "ok",
            "summary": f"{label} answered in {ping['latency_ms']:g} ms ({path}).",
            "latency_ms": ping["latency_ms"],
            "kind": ping["kind"],
            "relay": ping["relay"],
            "target_name": label,
        }


def _failure(result: Any) -> dict[str, Any]:
    combined = f"{result.stdout or ''}\n{result.stderr or ''}"
    if "login.tailscale.com" in combined:
        return {"success": False, "code": "needs_login", "summary": "Tailscale authorization is required on the host."}
    return {"success": False, "code": "command_failed", "summary": "VPN operation failed."}
