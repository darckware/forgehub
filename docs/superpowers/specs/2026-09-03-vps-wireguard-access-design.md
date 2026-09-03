# VPS WireGuard Access Design

**Status:** Proposed  
**Date:** 2026-09-03  
**Owner:** Marcelo  
**Target:** `vmi3547248`

## Objective

Create a private administration path between Marcelo's notebook and the VPS before installing the
remote Hermes/ForgeHub environment. The VPN must give the notebook access to services hosted on the
VPS without routing general Internet traffic through the VPS and without depending on the corporate
Cloudflare One organization configured on the notebook.

## Scope

This phase installs and validates WireGuard only. It does not install Hermes, copy agent profiles,
activate gateways, move cron jobs, deploy ForgeHub, change Telegram ownership, or federate the two
ForgeHub instances.

## Verified baseline

- VPS hostname: `vmi3547248`.
- Operating system: Ubuntu 24.04.
- Remote administration account: `aegis`.
- `aegis` has passwordless `sudo` and Docker group membership.
- The VPS has a public IPv4 address assigned directly to `eth0`; no provider-side NAT is required.
- UFW is active and currently permits public TCP ports 22, 80, and 443.
- WireGuard is not installed.
- `cloudflared` is installed and active, but a published `tcp://localhost:51820` route cannot carry
  WireGuard because WireGuard uses UDP.
- `vpn.darckware.net` currently resolves through Cloudflare's proxy rather than directly to the VPS.

## Network design

| Property | Value |
|---|---|
| VPN network | `10.77.0.0/24` |
| VPS WireGuard address | `10.77.0.1/24` |
| Notebook WireGuard address | `10.77.0.2/32` |
| VPS listen port | `51820/UDP` |
| Notebook routed destination | `10.77.0.1/32` only |
| Default-route tunnelling | Disabled |
| VPN-provided DNS | Disabled |
| IP forwarding/NAT | Disabled |
| Notebook keepalive | 25 seconds |

Only traffic addressed to the VPS WireGuard IP crosses the personal VPN. Corporate Cloudflare One
keeps ownership of the notebook's default route and DNS. The client must not contain
`AllowedIPs = 0.0.0.0/0` or an overlapping corporate/private subnet.

## Key handling

- Generate the VPS private key on the VPS with a restrictive umask and store it only under
  `/etc/wireguard` with mode `0600`.
- Generate the notebook private key on the notebook, outside Git and outside ForgeHub artifacts.
- Exchange public keys only.
- Never place either private key in Foundation, Hindsight, project documentation, command output,
  logs, or chat.
- A lost notebook is revoked by removing its peer public key from the VPS and restarting/reloading
  the WireGuard interface.

## Server configuration

Install the distribution-supported WireGuard package. Create `wg0` as a system-managed interface,
enable `wg-quick@wg0` at boot, and register the notebook as the sole initial peer with
`AllowedIPs = 10.77.0.2/32`.

No masquerade, forwarding, exit-node behavior, subnet routing, or access to another private network
is configured in this phase. The VPN terminates on the VPS itself.

UFW permits inbound `51820/UDP`. Existing public SSH access remains unchanged until the complete
VPN path has been proven from the notebook. Closing or restricting public SSH is a separate,
explicitly approved action after verification.

## Cloudflare DNS

The final client endpoint is `vpn.darckware.net:51820`, but only after the hostname is a DNS-only
`A` record pointing directly to the VPS public IPv4 address. A Cloudflare published-application
route and orange-cloud proxy are not valid transports for WireGuard UDP.

Initial validation may use the VPS public IPv4 address directly. This separates WireGuard health
from DNS propagation and prevents a DNS mistake from being misdiagnosed as a VPN failure.

## Validation

Server-side evidence:

1. `wg-quick@wg0` is enabled and active.
2. `wg show wg0` reports the intended listen port and peer without printing private keys.
3. `ip address show wg0` reports `10.77.0.1/24`.
4. UFW contains the intended UDP rule and no new unrelated exposure.
5. The service survives a controlled interface restart.

Notebook-to-VPS evidence:

1. WireGuard reports a recent authenticated handshake.
2. The notebook reaches `10.77.0.1`.
3. SSH authentication succeeds against `aegis@10.77.0.1`.
4. General Internet traffic and corporate DNS continue using their prior path.
5. Disconnecting WireGuard removes access to `10.77.0.1` without affecting normal connectivity.

The VPN is not considered complete until both server-side and notebook-side evidence pass.

## Failure handling

- If package installation fails, leave the existing SSH and firewall rules unchanged.
- If `wg0` fails to start, collect `systemctl status` and `journalctl` evidence, disable only the
  new unit, and preserve the generated server key for a corrected retry.
- If the notebook cannot handshake, verify endpoint, UDP reachability, public keys, clock, and
  corporate VPN interaction in that order.
- Do not modify corporate Cloudflare One policies or enrollment to make WireGuard work.
- Do not close public SSH during diagnosis.

## Rollback

Rollback stops and disables `wg-quick@wg0`, removes only the WireGuard UFW rule, and archives the
root-owned `wg0` configuration locally on the VPS with restricted permissions. Existing SSH,
Cloudflare, Docker, and application services remain unchanged. Package removal is unnecessary for
rollback and is avoided unless separately requested.

## Follow-up phases

After VPN verification, separate approved phases will cover:

1. VPS ForgeHub, databases, ForgeRouter, and Hindsight installation.
2. Staged copy of the eight persistent Hermes profiles with gateways and cron jobs disabled.
3. Agent-by-agent cutover with notebook instances retained as disabled standby.
4. ForgeHub-to-ForgeHub messaging federation over the private path.
5. Restriction of public administrative ports after private-access verification.
