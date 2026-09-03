from __future__ import annotations

import ipaddress
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from typing import Any, Callable


LOCAL_HOSTNAME = "NotebookSTI-wsl"
REMOTE_HOSTNAME = "vmi3547248"
TAILSCALE_NETWORK = ipaddress.ip_network("100.64.0.0/10")
ALLOWED_ACTIONS = {
    "local": frozenset({"connect", "disconnect", "restart", "test"}),
    "remote": frozenset({"restart", "test"}),
}
PRIVATE_KEY_ROOTS = ("/root/.ssh", "/root/agents", "/root/.hermes/profiles")


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


def _node(raw: object, *, role: str, backend_state: str) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}
    hostname = data.get("HostName") if isinstance(data.get("HostName"), str) else None
    if backend_state == "NeedsLogin" and role == "local":
        state = "needs_login"
    elif not hostname:
        state = "unavailable"
    else:
        state = "online" if data.get("Online") is True else "offline"
    return {
        "role": role,
        "hostname": hostname,
        "tailscale_ipv4": _tailscale_ipv4(data.get("TailscaleIPs")),
        "state": state,
        "online": data.get("Online") is True,
        "active": data.get("Active") is True,
        "last_seen": data.get("LastSeen") if isinstance(data.get("LastSeen"), str) else None,
        "rx_bytes": data.get("RxBytes") if isinstance(data.get("RxBytes"), int) else 0,
        "tx_bytes": data.get("TxBytes") if isinstance(data.get("TxBytes"), int) else 0,
    }


def parse_status(raw: str) -> dict[str, Any]:
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, TypeError) as exc:
        raise ValueError("invalid_response") from exc
    if not isinstance(payload, dict):
        raise ValueError("invalid_response")

    backend_state = payload.get("BackendState", "Unknown")
    local_raw = payload.get("Self")
    remote_raw: dict[str, Any] = {}
    peers = payload.get("Peer")
    if isinstance(peers, dict):
        for candidate in peers.values():
            if isinstance(candidate, dict) and candidate.get("HostName") == REMOTE_HOSTNAME:
                remote_raw = candidate
                break

    local = _node(local_raw, role="local", backend_state=str(backend_state))
    remote = _node(remote_raw, role="remote", backend_state=str(backend_state))
    if not remote["online"]:
        connection = {"kind": "unavailable", "relay": None}
    elif remote_raw.get("CurAddr"):
        connection = {"kind": "direct", "relay": None}
    elif remote_raw.get("Relay"):
        connection = {"kind": "derp", "relay": str(remote_raw["Relay"])}
    else:
        connection = {"kind": "idle", "relay": None}
    return {
        "backend_state": backend_state,
        "local": local,
        "remote": remote,
        "connection": connection,
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


class VpnControl:
    def __init__(
        self,
        runner: Callable[..., Any] = _default_runner,
        remote_user: str | None = None,
        remote_key_path: str | None = None,
        remote_host_key_alias: str | None = None,
    ) -> None:
        self.runner = runner
        self.remote_user = remote_user or os.environ.get("FORGEHUB_VPN_REMOTE_USER", "aegis")
        configured_key_path = remote_key_path or os.environ.get(
            "FORGEHUB_VPN_REMOTE_KEY_PATH",
            "/root/agents/aegis/server-management/ssh_keys/95_111_252_124_key",
        )
        self.remote_key_path = os.path.realpath(configured_key_path)
        if not any(
            self.remote_key_path == root or self.remote_key_path.startswith(f"{root}/")
            for root in PRIVATE_KEY_ROOTS
        ):
            raise VpnPolicyError("invalid_key_path")
        self.remote_host_key_alias = remote_host_key_alias or os.environ.get(
            "FORGEHUB_VPN_REMOTE_HOST_KEY_ALIAS", "95.111.252.124"
        )

    def status(self) -> dict[str, Any]:
        checked_at = datetime.now(timezone.utc).isoformat()
        try:
            result = self.runner(["tailscale", "status", "--json"], 10.0)
        except FileNotFoundError:
            return {
                "backend_state": "Unavailable",
                "local": _node({}, role="local", backend_state="Unavailable"),
                "remote": _node({}, role="remote", backend_state="Unavailable"),
                "connection": {"kind": "unavailable", "relay": None},
                "sources": [{"name": "status", "status": "unavailable", "checked_at": checked_at, "error_code": "binary_missing"}],
                "error": {"code": "binary_missing", "summary": "VPN status executable is unavailable."},
            }
        except subprocess.TimeoutExpired:
            return {
                "backend_state": "Unavailable",
                "local": _node({}, role="local", backend_state="Unavailable"),
                "remote": _node({}, role="remote", backend_state="Unavailable"),
                "connection": {"kind": "unavailable", "relay": None},
                "sources": [{"name": "status", "status": "unavailable", "checked_at": checked_at, "error_code": "timeout"}],
                "error": {"code": "timeout", "summary": "VPN status check timed out."},
            }
        if result.returncode != 0:
            return {
                "backend_state": "Unavailable",
                "local": _node({}, role="local", backend_state="Unavailable"),
                "remote": _node({}, role="remote", backend_state="Unavailable"),
                "connection": {"kind": "unavailable", "relay": None},
                "sources": [{"name": "status", "status": "unavailable", "checked_at": checked_at, "error_code": "daemon_unavailable"}],
                "error": {"code": "daemon_unavailable", "summary": "Tailscale status is unavailable."},
            }
        try:
            status = parse_status(result.stdout[:8192])
        except ValueError:
            return {
                "backend_state": "Unavailable",
                "local": _node({}, role="local", backend_state="Unavailable"),
                "remote": _node({}, role="remote", backend_state="Unavailable"),
                "connection": {"kind": "unavailable", "relay": None},
                "sources": [{"name": "status", "status": "unavailable", "checked_at": checked_at, "error_code": "invalid_response"}],
                "error": {"code": "invalid_response", "summary": "VPN status returned invalid data."},
            }

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
            posture = parse_prefs(prefs.stdout[:8192])
            sources.append({"name": "preferences", "status": "fresh", "checked_at": checked_at, "error_code": None})
        except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
            posture = None
            sources.append({"name": "preferences", "status": "unavailable", "checked_at": checked_at, "error_code": "probe_failed"})

        status["local"]["daemon_state"] = daemon_state
        status["local"]["posture"] = posture
        status["remote"]["daemon_state"] = "observed" if status["remote"]["online"] else "unavailable"
        status["remote"]["posture"] = None
        status["sources"] = sources
        return status

    def action(self, node: str, action: str) -> dict[str, Any]:
        if node not in ALLOWED_ACTIONS or action not in ALLOWED_ACTIONS[node]:
            raise VpnPolicyError("action_not_allowed")

        if action == "connect":
            argv = [
                "tailscale",
                "up",
                "--hostname=NotebookSTI-wsl",
                "--accept-dns=false",
                "--accept-routes=false",
                "--advertise-exit-node=false",
                "--ssh=false",
            ]
            timeout = 30.0
        elif action == "disconnect":
            argv = ["tailscale", "down"]
            timeout = 15.0
        elif action == "restart" and node == "local":
            argv = ["systemctl", "restart", "tailscaled"]
            timeout = 30.0
        elif action == "restart" and node == "remote":
            status = self.status()
            remote_ip = status["remote"].get("tailscale_ipv4")
            if not remote_ip:
                return {"success": False, "code": "peer_offline", "summary": "Remote peer is unavailable."}
            argv = [
                "ssh",
                "-i",
                self.remote_key_path,
                "-o",
                "BatchMode=yes",
                "-o",
                "ConnectTimeout=8",
                "-o",
                f"HostKeyAlias={self.remote_host_key_alias}",
                f"{self.remote_user}@{remote_ip}",
                "sudo",
                "-n",
                "systemctl",
                "restart",
                "tailscaled",
            ]
            timeout = 20.0
        elif action == "test":
            status = self.status()
            remote_ip = status["remote"].get("tailscale_ipv4")
            if not remote_ip:
                return {"success": False, "code": "peer_offline", "summary": "Remote peer is unavailable."}
            argv = ["tailscale", "ping", "--until-direct=false", "--c", "1", remote_ip]
            timeout = 15.0
        else:
            raise VpnPolicyError("action_not_implemented")

        try:
            result = self.runner(argv, timeout)
        except FileNotFoundError:
            return {"success": False, "code": "binary_missing", "summary": "VPN operation executable is unavailable."}
        except subprocess.TimeoutExpired:
            return {"success": False, "code": "timeout", "summary": "VPN operation timed out."}
        if result.returncode != 0:
            combined = f"{result.stdout}\n{result.stderr}"
            code = "needs_login" if "login.tailscale.com" in combined else "command_failed"
            summary = "Tailscale authorization is required on the host." if code == "needs_login" else "VPN operation failed."
            return {"success": False, "code": code, "summary": summary}
        if action == "test":
            return parse_ping(result.stdout[:8192])
        if action == "restart":
            fresh = self.status()
            target = fresh[node]
            if target.get("state") != "online":
                return {"success": False, "code": "peer_offline", "summary": "VPN node did not return online."}
        return {"success": True, "code": "ok", "summary": "VPN operation completed."}
