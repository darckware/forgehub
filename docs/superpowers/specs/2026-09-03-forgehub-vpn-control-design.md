# ForgeHub VPN Control Design

**Status:** Approved for implementation  
**Date:** 2026-09-03  
**Owner:** Marcelo  
**Scope:** Development-mode operational control for the existing Tailscale link

## Objective

Add an administrator-only **VPN** screen to ForgeHub that explains and controls the active
Tailscale path between Ubuntu WSL `NotebookSTI-wsl` and VPS `vmi3547248`. The screen must expose
live evidence without exposing credentials, accepting arbitrary commands, or creating a dependency
on public ICMP, SSH, HTTP, or HTTPS listeners.

## Network boundaries

Cloudflare and Tailscale have separate responsibilities:

- Cloudflare Tunnel is the application presentation and recovery plane. `cloudflared` establishes
  outbound connections from the VPS, so a later production-hardening phase can close public inbound
  ports while keeping approved applications reachable through Cloudflare.
- Tailscale is the private administration plane. The two nodes establish outbound coordination and
  data paths through Tailscale. A direct peer path is optional; DERP relay operation is healthy.
- The existing Cloudflare One client on Windows remains the notebook's corporate network layer.
  This feature does not edit its organization, enrollment, DNS, routes, or split-tunnel policy.
- A `cloudflared` tunnel is not presented as a proxy for Tailscale packets. The UI reports the
  observed Tailscale path (`direct` or `DERP`) rather than claiming Cloudflare mediation that cannot
  be verified from Tailscale state.

The development implementation does not change UFW, Cloudflare, DNS, public listeners, or the
Tailscale policy file. Closing public ingress is a separate production-hardening change after a
recovery path is proven.

## Authorized topology

| Role | Node | Current purpose |
|---|---|---|
| Local controller | `NotebookSTI-wsl` | Runs ForgeHub's host bridge and the local Tailscale client |
| Remote target | `vmi3547248` | Hosts the remote Tailscale peer and future remote ForgeHub services |

Node identity is resolved from `tailscale status --json` by hostname and Tailscale identity. The
implementation must not hardcode a `100.x` address because Tailscale addresses are operational
state. Remote operations use only the resolved private Tailscale address. The remote SSH user and
identity-file path come from operator configuration or the registered ForgeHub Server record and
are never returned to the browser.

## User experience

Add an administrator-only sidebar entry named **VPN** with route `/vpn`. The page contains:

1. A topology summary that labels Cloudflare as the application plane and Tailscale as the private
   administration plane.
2. One status card per node showing hostname, Tailscale IPv4, online state, daemon state, last seen,
   traffic counters, and restricted posture.
3. A connection card showing `direct`, `DERP <region>`, `idle`, or `unavailable`, plus the last
   successful Tailscale diagnostic and latency when known.
4. Local-node actions: **Connect**, **Disconnect**, **Restart**, and **Test connection**.
5. Remote-node actions: **Restart** and **Test connection**. There is deliberately no remote
   disconnect action because disconnecting the remote peer would remove the channel needed to
   reconnect it.
6. A recent-operations list with actor, target, action, result, timestamp, and a sanitized summary.

The page polls read-only status every 10 seconds while visible and refreshes immediately after an
action. Loading, empty, partial-failure, action-in-progress, success, and failure states must keep
their layout stable. Disruptive local actions require an in-app confirmation dialog. Controls are
disabled while the same node has an action in flight.

The screen never displays authentication URLs, auth keys, OAuth credentials, private keys, SSH key
paths, cookies, raw command lines, or unrestricted stdout/stderr.

## Backend API

Create an admin-only router at `/api/v1/vpn`:

- `GET /status` returns the aggregate topology, both nodes, observed connection path, posture, and
  per-source freshness/errors.
- `POST /nodes/{node}/actions` accepts an action enum. `local` allows `connect`, `disconnect`,
  `restart`, and `test`; `remote` allows only `restart` and `test`.
- `GET /operations?limit=N` returns sanitized recent operation records with a bounded limit.

All routes use `get_current_admin`. Browser requests use the existing JWT boundary; the backend
uses `CHAT_BRIDGE_TOKEN` only for its internal request to the host bridge. The generic bridge-token
middleware bypass must not be extended to make VPN browser routes public.

The aggregate response represents partial availability explicitly. If local status succeeds but a
remote probe fails, the API returns the local node plus an `unavailable` remote node and an
actionable sanitized error; it does not turn the whole page into HTTP 500.

## Host bridge adapter

Add dedicated authenticated endpoints under `/v1/vpn`. They accept only logical node identifiers
and action enums; they do not accept commands, executable names, flags, hostnames, IPs, usernames,
or file paths from the caller.

The adapter invokes subprocesses with argument arrays, fixed timeouts, bounded output, and no shell:

- Local status: `tailscale status --json`, `tailscale debug prefs`, and systemd state.
- Local connect: `tailscale up` with hostname fixed to `NotebookSTI-wsl`, DNS/routes disabled, no
  advertised exit node, and Tailscale SSH disabled.
- Local disconnect: `tailscale down`.
- Local restart: restart `tailscaled`, wait for `Running`, then report fresh status.
- Connection test: `tailscale ping --until-direct=false` to the private identity resolved from live
  status. Ordinary ICMP is not required.
- Remote restart: use the private Tailscale IPv4 and the configured SSH identity to run only the
  fixed `sudo -n systemctl restart tailscaled` operation. The adapter verifies the trusted host key,
  waits for the peer to return, and never falls back to the public IP.

If the remote node is offline, remote restart is unavailable because there is no safe path to it.
Recovery then belongs to the separately configured Cloudflare/provider recovery plane. The UI must
say this directly instead of offering an action that cannot work.

## Operational audit

Create a `company.vpn_operation_events` table with UUID primary key and `TimestampMixin`. Each
action records:

- requesting user ID;
- logical target (`local` or `remote`);
- allow-listed action;
- lifecycle status (`running`, `succeeded`, or `failed`);
- start/completion timestamps;
- sanitized result/error code and summary.

No credential, authentication URL, private key material, raw subprocess output, or bridge token is
stored. Read-only polling is not persisted; only explicit operator actions create events.

## Safety rules

- Administrator access is enforced server-side, not only by hiding the sidebar item.
- No arbitrary-command endpoint is added.
- No endpoint can change UFW, Cloudflare, tailnet ACLs, MagicDNS, exit nodes, subnet routes,
  Tailscale Serve/Funnel, or Tailscale SSH.
- The remote node cannot be disconnected from ForgeHub.
- Remote actions never fall back to a public address.
- Failed and timed-out operations are visible and audit-recorded without leaking raw output.
- A frontend confirmation is usability protection; backend allow-lists remain the authority.

## Testing

Backend and bridge tests cover:

- admin authorization and non-admin rejection;
- command/action allow-lists and rejection of unknown nodes/actions;
- parsing direct, DERP, idle, offline, `NeedsLogin`, and malformed Tailscale status;
- fixed safe preferences on connect;
- remote resolution from live identity rather than a hardcoded IP;
- no public-IP fallback and no remote disconnect;
- partial status when one source is unavailable;
- timeout/error sanitization and operation-event transitions;
- absence of secrets and raw command output in API responses and persisted events.

Frontend tests cover:

- admin-only navigation and route behavior;
- node, posture, connection-path, partial-failure, and empty states;
- confirmations and per-node action locking;
- cache refresh after actions;
- accessible names, keyboard operation, and responsive layout.

Verification includes focused pytest and Vitest suites, full frontend build, backend lint for touched
modules, and a browser smoke test against `./dev.sh`. Live smoke validation must prove status and a
non-disruptive connection test. Restart/disconnect smoke actions require explicit operator intent
at execution time.

## Out of scope

- Closing public firewall ports or changing UFW.
- Editing Cloudflare Tunnel, Cloudflare One, DNS, or Zero Trust policy.
- Tailscale administrative API credentials, device deletion, ACL/grant edits, or key rotation.
- Enabling Tailscale SSH, MagicDNS, Serve, Funnel, exit nodes, or subnet routes.
- A generic multi-provider VPN framework.
- A remote outbound ForgeHub control agent; this becomes necessary only if private SSH is also
  prohibited or remote recovery must work while Tailscale itself is down.
