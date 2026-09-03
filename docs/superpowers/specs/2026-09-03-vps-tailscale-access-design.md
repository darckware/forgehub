# VPS Tailscale Access Design

**Status:** Approved for implementation
**Date:** 2026-09-03  
**Owner:** Marcelo  
**Target:** `vmi3547248`

## Objective

Create a private administration path between Marcelo's Ubuntu WSL environment and the VPS before
installing the remote Hermes/ForgeHub environment. The path must not open a new inbound port, alter
the Windows host's corporate Cloudflare One enrollment, provide an Internet exit node, or take
control of system DNS.

## Scope

This phase installs and validates Tailscale on the VPS and in Ubuntu WSL. It does not install a
Tailscale client on Windows, install Hermes, copy agent profiles, activate gateways, move cron jobs,
deploy ForgeHub, change Telegram ownership, or federate ForgeHub instances.

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
- The local execution environment is Ubuntu on WSL 2 and does not currently have Tailscale.

## Topology

The VPS and Ubuntu WSL join a personal tailnet as separate devices. Tailscale runs inside WSL and
is not installed as a second node on the Windows host. Windows applications do not receive a
tailnet route; browser access to remote services uses a loopback forward owned by WSL.

| Property | Value |
|---|---|
| VPS node name | `vmi3547248` |
| Notebook node | Ubuntu WSL only (`NotebookSTI`) |
| DNS acceptance | Disabled on both tailnet nodes for the pilot |
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

Cloudflare One remains connected on Windows and retains the Windows default route and DNS.
Tailscale changes only the WSL network namespace and must not use an exit node, accept tailnet DNS,
or advertise routes. Its encrypted control and peer traffic exits through the normal WSL-to-Windows
network path. No corporate Cloudflare policy is changed by this work.

The pilot stops if corporate Internet access, DNS, private resources, posture, or policy behavior
changes. Compatibility is proven on the actual WSL/Windows pair; documentation-level compatibility
is not treated as operational evidence.

Tailscale must be installed in Ubuntu WSL only. Installing it later on Windows at the same time
would create two tailnet nodes and can cause nested encapsulation and MTU problems.

## Authentication and authorization

- Use a personal Tailscale organization, separate from the corporate Cloudflare organization.
- Enroll the VPS through the one-time Tailscale authorization URL emitted by `tailscale up`; the
  operator completes authentication in the browser.
- Do not paste reusable auth keys, OAuth secrets, or session cookies into chat, Git, Foundation,
  Hindsight, or logs.
- After enrollment, identify the VPS by node identity and restrict access so only the `NotebookSTI`
  WSL node can reach it.
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

## Windows browser access

Windows does not join the tailnet in this design. To open ForgeHub VPS in the Windows browser, WSL
creates a loopback-only forward from a dedicated local port to the ForgeHub service on the VPS
Tailscale address. Windows reaches the WSL loopback through WSL's localhost forwarding behavior.

The forward must bind only to `127.0.0.1`, never `0.0.0.0`, and must not become a public listener on
the notebook. The initial validation uses a temporary foreground SSH forward. A persistent local
proxy is considered only in the later ForgeHub deployment phase.

## Validation

VPS evidence:

1. `tailscaled` is enabled and active.
2. `tailscale status` reports the VPS authenticated in the intended personal tailnet.
3. `tailscale ip -4` returns one address in `100.64.0.0/10`.
4. `tailscale netcheck` completes without requiring a new inbound firewall rule.
5. UFW contains no new public application port from this phase.

WSL and Windows-host evidence, with Cloudflare One connected throughout:

1. Corporate Internet, DNS, and authorized company resources work before and after Tailscale starts.
2. The WSL Tailscale client authenticates into the personal tailnet without changing the Windows
   Cloudflare Zero Trust organization.
3. `tailscale ping` from WSL to the assigned VPS Tailscale IPv4 address succeeds and reports whether the
   path is direct or relayed.
4. SSH to the `aegis` account at the assigned VPS Tailscale IPv4 address succeeds from WSL.
5. A loopback-only WSL forward lets the Windows browser reach a test HTTP service over the tailnet.
6. Stopping Tailscale in WSL removes the private path without disturbing Cloudflare One connectivity.

The private access phase is not complete until both VPS and Windows/WSL evidence pass.

## Failure handling

- If repository or package installation fails, leave Cloudflare, UFW, SSH, and Docker unchanged.
- If VPS enrollment is not completed, stop after presenting the one-time browser authorization URL.
- If Tailscale connects but no peer path exists, inspect `tailscale status`, `tailscale ping`, and
  `tailscale netcheck`; relay operation is acceptable and no public port is opened as a workaround.
- If Cloudflare One connectivity changes, stop Tailscale in WSL and restore the pre-test state.
- Do not change corporate Cloudflare split-tunnel, DNS, enrollment, or MDM policies.
- Do not install a second Tailscale node on Windows to work around browser routing.
- Do not close public SSH while diagnosing the pilot.

## Rollback

Rollback runs `tailscale down` in WSL and on the VPS, disables `tailscaled` on the VPS, and removes
the temporary loopback forward if one is active. It leaves the packages installed to preserve a
low-risk retry path and does not remove existing Cloudflare, SSH, Docker, DNS, or firewall
configuration. Both new nodes can then be removed from the personal tailnet via the Tailscale admin
console. Package removal and DNS deletion require separate explicit approval.

## Follow-up phases

After private-access verification, separate approved phases will cover:

1. VPS ForgeHub, databases, ForgeRouter, and Hindsight installation.
2. Staged copy of the eight persistent Hermes profiles with gateways and cron jobs disabled.
3. Agent-by-agent cutover with notebook instances retained as disabled standby.
4. ForgeHub-to-ForgeHub messaging federation over Tailscale.
5. Restriction of public administrative ports after recovery-path verification.
