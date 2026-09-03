# VPS Tailscale Access Design

**Status:** Proposed  
**Date:** 2026-09-03  
**Owner:** Marcelo  
**Target:** `vmi3547248`

## Objective

Create a private administration path between Marcelo's Windows/WSL notebook and the VPS before
installing the remote Hermes/ForgeHub environment. The path must not open a new inbound port, alter
the notebook's corporate Cloudflare One enrollment, provide an Internet exit node, or take control
of system DNS.

## Scope

This phase installs and validates Tailscale on the VPS and pairs a Tailscale client on the Windows
host. It does not install Hermes, copy agent profiles, activate gateways, move cron jobs, deploy
ForgeHub, change Telegram ownership, or federate ForgeHub instances.

## Verified baseline

- VPS hostname: `vmi3547248`.
- Operating system: Ubuntu 24.04.
- Remote administration account: `aegis`.
- `aegis` has passwordless `sudo` and Docker group membership.
- UFW is active; no Tailscale-specific inbound rule exists.
- The VPS can reach Tailscale's package and login endpoints over HTTPS.
- Tailscale is not installed in the VPS or the current WSL environment.
- Cloudflare One is enrolled in a separate corporate organization on the Windows host.
- `cloudflared` is active on the VPS, but it is not part of this private-network path.
- `vpn.darckware.net` is currently a Cloudflare-proxied published TCP application route and is not
  a usable Tailscale endpoint in that form.
- Windows service inspection from the current sandbox is unavailable, so the Windows client state
  must be verified during the client-side pilot.

## Topology

The VPS and Windows host join a personal tailnet as separate devices. Tailscale runs on Windows,
not as a second node inside WSL. WSL traffic is tested through the Windows host route.

| Property | Value |
|---|---|
| VPS node name | `vmi3547248` |
| Notebook node | Windows host only |
| DNS acceptance | Disabled on both nodes for the pilot |
| Exit node | Disabled |
| Subnet routes | None |
| Funnel/Serve publication | Disabled |
| New public firewall ports | None |
| Initial access address | VPS Tailscale `100.x` address |
| Friendly alias after validation | `vpn.darckware.net` |

Tailscale may establish a direct encrypted path through NAT traversal or use a DERP relay. Either
path is acceptable for the pilot. Opening UDP 41641 is an optional performance optimization and is
explicitly outside this phase.

## Cloudflare coexistence

Cloudflare One remains connected first and retains the notebook's default route and DNS. Tailscale
must not use an exit node, accept tailnet DNS, or advertise routes. The pilot relies on the
Cloudflare client's normal exclusion of the `100.64.0.0/10` CGNAT range; no corporate Cloudflare
policy is changed by this work.

The pilot stops if corporate Internet access, DNS, private resources, posture, or policy behavior
changes. Compatibility is proven only on the actual Windows host; documentation-level
compatibility is not treated as operational evidence.

Tailscale must be installed on the Windows host only. Installing it simultaneously on Windows and
inside WSL would create two tailnet nodes and can cause nested encapsulation and MTU problems.

## Authentication and authorization

- Use a personal Tailscale organization, separate from the corporate Cloudflare organization.
- Enroll the VPS through the one-time Tailscale authorization URL emitted by `tailscale up`; the
  operator completes authentication in the browser.
- Do not paste reusable auth keys, OAuth secrets, or session cookies into chat, Git, Foundation,
  Hindsight, or logs.
- After enrollment, identify the VPS by node identity and restrict access so only Marcelo's
  notebook identity can reach it.
- Do not enable Tailscale SSH until the base IP path is verified. Initial SSH continues to use the
  existing `aegis` account and key over the Tailscale IP.

## VPS installation

Install the stable Tailscale package from the official Ubuntu repository, enable `tailscaled`, and
bring the node up with hostname `vmi3547248`, DNS acceptance disabled, and no advertised routes or
exit-node capability.

No existing UFW rule is removed during installation. Public SSH remains available until the full
notebook-to-VPS path and recovery path have passed validation. Restricting public SSH is a later,
separately approved action.

## Friendly DNS alias

Tailscale does not need `vpn.darckware.net` for transport or coordination. Initial tests use the
assigned `100.x` address.

After validation, `vpn.darckware.net` may become a DNS-only `A` record whose value is the VPS
Tailscale IPv4 address. It must not be orange-cloud proxied and must not remain a Cloudflare
published-application route. The address is intentionally unreachable to devices outside the
tailnet. HTTPS certificate handling for ForgeHub is a later phase; this alias initially provides
name-to-private-IP resolution only.

## Validation

VPS evidence:

1. `tailscaled` is enabled and active.
2. `tailscale status` reports the VPS authenticated in the intended personal tailnet.
3. `tailscale ip -4` returns one address in `100.64.0.0/10`.
4. `tailscale netcheck` completes without requiring a new inbound firewall rule.
5. UFW contains no new public application port from this phase.

Windows and WSL evidence, with Cloudflare One connected first:

1. Corporate Internet, DNS, and authorized company resources work before and after Tailscale starts.
2. The Windows Tailscale client authenticates into the personal tailnet without changing the
   Cloudflare Zero Trust organization.
3. `tailscale ping` to the assigned VPS Tailscale IPv4 address succeeds and reports whether the
   path is direct or relayed.
4. SSH to the `aegis` account at the assigned VPS Tailscale IPv4 address succeeds from Windows.
5. WSL reaches the VPS Tailscale IP and can use the required ForgeHub/SSH path through Windows.
6. Stopping Tailscale removes the private path without disturbing Cloudflare One connectivity.

The private access phase is not complete until both VPS and Windows/WSL evidence pass.

## Failure handling

- If repository or package installation fails, leave Cloudflare, UFW, SSH, and Docker unchanged.
- If VPS enrollment is not completed, stop after presenting the one-time browser authorization URL.
- If Tailscale connects but no peer path exists, inspect `tailscale status`, `tailscale ping`, and
  `tailscale netcheck`; relay operation is acceptable and no public port is opened as a workaround.
- If Cloudflare One connectivity changes, stop Tailscale on Windows and restore the pre-test state.
- Do not change corporate Cloudflare split-tunnel, DNS, enrollment, or MDM policies.
- Do not install a second Tailscale node inside WSL to work around Windows routing.
- Do not close public SSH while diagnosing the pilot.

## Rollback

Rollback runs `tailscale down` on the new nodes and disables `tailscaled` on the VPS. It leaves the
package installed to preserve a low-risk retry path and does not remove existing Cloudflare, SSH,
Docker, DNS, or firewall configuration. The VPS can then be removed from the personal tailnet via
the Tailscale admin console. Package removal and DNS deletion require separate explicit approval.

## Follow-up phases

After private-access verification, separate approved phases will cover:

1. VPS ForgeHub, databases, ForgeRouter, and Hindsight installation.
2. Staged copy of the eight persistent Hermes profiles with gateways and cron jobs disabled.
3. Agent-by-agent cutover with notebook instances retained as disabled standby.
4. ForgeHub-to-ForgeHub messaging federation over Tailscale.
5. Restriction of public administrative ports after recovery-path verification.
