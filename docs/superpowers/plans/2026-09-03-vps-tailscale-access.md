# VPS Tailscale Access Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Establish and verify a private Tailscale path from Ubuntu WSL `NotebookSTI` to VPS `vmi3547248` without opening a new public port or changing corporate Cloudflare One.

**Architecture:** Install one Tailscale node in Ubuntu WSL and one on the VPS. Both nodes use a personal tailnet, decline Tailscale DNS and routes, and leave Cloudflare One on Windows untouched; the VPS may use DERP rather than exposing UDP.

**Tech Stack:** Ubuntu 24.04, systemd, Tailscale stable packages, OpenSSH, UFW, WSL 2

**Spec:** `docs/superpowers/specs/2026-09-03-vps-tailscale-access-design.md`

## Global Constraints

- Install Tailscale in Ubuntu WSL and the VPS only; do not install it on Windows.
- Do not enable exit-node, subnet-router, MagicDNS, Tailscale Serve, Funnel, or Tailscale SSH.
- Do not add or remove UFW rules during this phase.
- Do not change corporate Cloudflare One enrollment, DNS, routes, MDM, or split-tunnel policy.
- Keep public SSH available until private-path and recovery checks pass.
- Do not persist auth URLs, reusable auth keys, OAuth secrets, cookies, or private keys in Git, chat, Foundation, Hindsight, or logs.
- Do not install Hermes, ForgeHub, ForgeRouter, Hindsight, or agent profiles in this phase.

---

### Task 1: Capture the pre-install baseline

**Files:**
- Read: `docs/superpowers/specs/2026-09-03-vps-tailscale-access-design.md`
- Read: `/etc/os-release` on WSL and VPS
- Read: UFW and systemd state on the VPS

**Interfaces:**
- Consumes: Existing SSH key and `aegis` sudo access registered for `vmi3547248`
- Produces: Fresh evidence that installation prerequisites and rollback access are intact

- [ ] **Step 1: Verify local WSL baseline**

Run:

```bash
test "$(. /etc/os-release; printf '%s' "$VERSION_CODENAME")" = noble
test "$(systemd-detect-virt)" = wsl
! command -v tailscale
curl -fsS --max-time 15 https://login.tailscale.com/ -o /dev/null
```

Expected: all commands exit 0; Tailscale is absent and outbound HTTPS works.

- [ ] **Step 2: Verify VPS baseline through the registered key**

Run:

```bash
ssh -i /root/agents/aegis/server-management/ssh_keys/95_111_252_124_key \
  -p 22 -o BatchMode=yes -o ConnectTimeout=8 aegis@95.111.252.124 \
  'set -eu; sudo -n true; test "$(. /etc/os-release; printf %s "$VERSION_CODENAME")" = noble; ! command -v tailscale; sudo ufw status; curl -fsS --max-time 15 https://login.tailscale.com/ -o /dev/null'
```

Expected: exit 0, UFW active, Tailscale absent, HTTPS available.

- [ ] **Step 3: Confirm existing public recovery access remains functional**

Run:

```bash
ssh -i /root/agents/aegis/server-management/ssh_keys/95_111_252_124_key \
  -p 22 -o BatchMode=yes -o ConnectTimeout=8 aegis@95.111.252.124 \
  'hostname; id -un; sudo -n true'
```

Expected: `vmi3547248`, `aegis`, exit 0.

### Task 2: Install and enroll Tailscale on the VPS

**Files:**
- Create remotely: `/usr/share/keyrings/tailscale-archive-keyring.gpg`
- Create remotely: `/etc/apt/sources.list.d/tailscale.list`
- Managed remotely by package: `/etc/systemd/system/multi-user.target.wants/tailscaled.service`

**Interfaces:**
- Consumes: Official Tailscale Ubuntu Noble package repository and operator browser authorization
- Produces: Authenticated `vmi3547248` tailnet node with DNS/routes disabled

- [ ] **Step 1: Add the official Tailscale repository on the VPS**

Run through the existing SSH connection:

```bash
curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.noarmor.gpg \
  | sudo tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null
curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.tailscale-keyring.list \
  | sudo tee /etc/apt/sources.list.d/tailscale.list >/dev/null
```

Expected: both files exist, are non-empty, and no credential is printed.

- [ ] **Step 2: Install and start the VPS daemon**

Run:

```bash
sudo apt-get update
sudo apt-get install -y tailscale
sudo systemctl enable --now tailscaled
systemctl is-active tailscaled
systemctl is-enabled tailscaled
```

Expected: both final checks print `active` and `enabled`.

- [ ] **Step 3: Start restricted VPS enrollment**

Run:

```bash
sudo tailscale up \
  --hostname=vmi3547248 \
  --accept-dns=false \
  --accept-routes=false \
  --advertise-exit-node=false \
  --ssh=false
```

Expected: Tailscale prints a one-time browser authorization URL and waits for authorization.

- [ ] **Step 4: Pause for operator authorization**

Action: Marcelo opens the one-time URL, signs into the personal Tailscale organization, and approves only the VPS node.

Expected: `sudo tailscale status` stops reporting `NeedsLogin` and shows `vmi3547248`.

- [ ] **Step 5: Verify VPS posture without printing secrets**

Run:

```bash
sudo tailscale status
sudo tailscale ip -4
sudo tailscale netcheck
sudo tailscale debug prefs | grep -E 'CorpDNS|RouteAll|ExitNodeID|AdvertiseRoutes|RunSSH'
sudo ufw status
```

Expected: one `100.x` IPv4 address; DNS, route acceptance, advertised routes, exit node, and Tailscale SSH remain disabled; UFW has no new rule.

### Task 3: Install and enroll Tailscale inside Ubuntu WSL

**Files:**
- Create locally: `/usr/share/keyrings/tailscale-archive-keyring.gpg`
- Create locally: `/etc/apt/sources.list.d/tailscale.list`
- Managed locally by package: `/etc/systemd/system/multi-user.target.wants/tailscaled.service`

**Interfaces:**
- Consumes: Official Tailscale Ubuntu Noble repository and the same personal tailnet identity used in Task 2
- Produces: Authenticated `NotebookSTI-wsl` node with no DNS, accepted routes, or exit-node behavior

- [ ] **Step 1: Add the official repository inside WSL**

Run:

```bash
curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.noarmor.gpg \
  | sudo tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null
curl -fsSL https://pkgs.tailscale.com/stable/ubuntu/noble.tailscale-keyring.list \
  | sudo tee /etc/apt/sources.list.d/tailscale.list >/dev/null
```

Expected: both files exist and are non-empty.

- [ ] **Step 2: Install and start the WSL daemon**

Run:

```bash
sudo apt-get update
sudo apt-get install -y tailscale
sudo systemctl enable --now tailscaled
systemctl is-active tailscaled
systemctl is-enabled tailscaled
```

Expected: `active` and `enabled`.

- [ ] **Step 3: Start restricted WSL enrollment**

Run:

```bash
sudo tailscale up \
  --hostname=NotebookSTI-wsl \
  --accept-dns=false \
  --accept-routes=false \
  --advertise-exit-node=false \
  --ssh=false
```

Expected: a one-time authorization URL for the WSL node.

- [ ] **Step 4: Pause for operator authorization**

Action: Marcelo authorizes `NotebookSTI-wsl` in the same personal tailnet as `vmi3547248`.

Expected: `sudo tailscale status` lists both nodes and no unrelated device.

- [ ] **Step 5: Verify local restricted posture**

Run:

```bash
sudo tailscale status
sudo tailscale ip -4
sudo tailscale netcheck
sudo tailscale debug prefs | grep -E 'CorpDNS|RouteAll|ExitNodeID|AdvertiseRoutes|RunSSH'
```

Expected: one local `100.x` IPv4 address and restricted preferences matching the spec.

### Task 4: Prove coexistence and private access

**Files:**
- Read: WSL `/etc/resolv.conf` and route table
- Read remotely: VPS Tailscale and SSH status
- No persistent files created

**Interfaces:**
- Consumes: Both authenticated tailnet nodes from Tasks 2 and 3
- Produces: Evidence that WSL can administer the VPS while Windows Cloudflare One remains unaffected

- [ ] **Step 1: Resolve the VPS Tailscale IP without hardcoding it**

Run in WSL:

```bash
VPS_TS_IP="$(sudo tailscale status --json | jq -r '.Peer | to_entries[] | select(.value.HostName == "vmi3547248") | .value.TailscaleIPs[0]' | head -n 1)"
test -n "$VPS_TS_IP"
printf 'vps_tailscale_ip=%s\n' "$VPS_TS_IP"
```

Expected: a single address inside `100.64.0.0/10`.

- [ ] **Step 2: Verify Tailscale transport**

Run:

```bash
sudo tailscale ping "$VPS_TS_IP"
ping -c 3 "$VPS_TS_IP"
```

Expected: authenticated Tailscale ping succeeds; ICMP succeeds. Direct or DERP paths are both accepted.

- [ ] **Step 3: Verify SSH over Tailscale**

Run:

```bash
ssh -i /root/agents/aegis/server-management/ssh_keys/95_111_252_124_key \
  -o BatchMode=yes -o ConnectTimeout=8 "aegis@$VPS_TS_IP" \
  'hostname; id -un; sudo -n true'
```

Expected: `vmi3547248`, `aegis`, exit 0.

- [ ] **Step 4: Verify WSL Internet and DNS remain operational**

Run:

```bash
getent ahostsv4 login.tailscale.com
curl -fsS --max-time 15 https://login.tailscale.com/ -o /dev/null
ip route show default
```

Expected: DNS and HTTPS succeed; the WSL default route remains its original Windows/WSL gateway rather than `tailscale0`.

- [ ] **Step 5: Obtain operator confirmation for corporate Cloudflare behavior**

Action: Marcelo confirms in Windows that ordinary Internet, corporate DNS, and an authorized company resource still work while WSL Tailscale is connected.

Expected: explicit confirmation; otherwise run `sudo tailscale down` in WSL and stop the pilot.

- [ ] **Step 6: Verify disconnect behavior, then reconnect**

Run:

```bash
sudo tailscale down
! ping -c 1 -W 2 "$VPS_TS_IP"
curl -fsS --max-time 15 https://login.tailscale.com/ -o /dev/null
sudo tailscale up \
  --hostname=NotebookSTI-wsl \
  --accept-dns=false \
  --accept-routes=false \
  --advertise-exit-node=false \
  --ssh=false
sudo tailscale ping "$VPS_TS_IP"
```

Expected: private IP is unavailable while down, normal HTTPS remains available, and private connectivity returns without re-enrollment.

### Task 5: Document operations and preserve rollback

**Files:**
- Create: `docs/guides/VPS_TAILSCALE_OPERATIONS.md`
- Modify: `docs/superpowers/specs/2026-09-03-vps-tailscale-access-design.md`

**Interfaces:**
- Consumes: Verified node names, non-secret Tailscale IPs, connection type, and validation evidence
- Produces: Sanitized operational runbook and implemented spec status

- [ ] **Step 1: Write the operations runbook**

Create `docs/guides/VPS_TAILSCALE_OPERATIONS.md` with:

```markdown
# VPS Tailscale Operations

## Topology

- Notebook node: `NotebookSTI-wsl`
- VPS node: `vmi3547248`
- DNS: Tailscale DNS disabled
- Routes: no exit node or advertised subnet
- Public firewall: no Tailscale-specific inbound rule

## Health

Run `tailscale status`, `tailscale netcheck`, and `tailscale ping` from WSL. On the VPS, verify
`systemctl is-active tailscaled` and `tailscale status`.

## Recovery access

Keep the registered public SSH path until a separate hardening change is approved and verified.

## Rollback

Run `sudo tailscale down` on WSL and VPS, then `sudo systemctl disable --now tailscaled` on the VPS.
Do not remove Cloudflare, SSH, Docker, DNS, or firewall configuration as part of VPN rollback.
```

- [ ] **Step 2: Mark the spec implemented only after all evidence passes**

Change the spec status from `Approved for implementation` to `Implemented and verified`. If any Windows corporate check remains unconfirmed, use `Server installed; client validation pending` instead.

- [ ] **Step 3: Run documentation verification**

Run:

```bash
rg -n 'TBD|TODO|PLACEHOLDER|0\.0\.0\.0/0|advertise-routes|advertise-exit-node=true' \
  docs/guides/VPS_TAILSCALE_OPERATIONS.md \
  docs/superpowers/specs/2026-09-03-vps-tailscale-access-design.md
git diff --check
```

Expected: `rg` finds only the explicit prohibition of `0.0.0.0/0` in the design, no unsafe enabled setting, and `git diff --check` exits 0.

- [ ] **Step 4: Commit verified operations documentation**

Run:

```bash
git add docs/guides/VPS_TAILSCALE_OPERATIONS.md \
  docs/superpowers/specs/2026-09-03-vps-tailscale-access-design.md
git commit -m "Infra: document VPS Tailscale operations"
```

Expected: one commit containing only the runbook and final spec status.
