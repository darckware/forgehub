# ForgeHub VPN Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an administrator-only ForgeHub VPN page that safely observes and controls the independent Tailscale link between `NotebookSTI-wsl` and `vmi3547248`.

**Architecture:** A dedicated host-bridge adapter owns every privileged Tailscale and private-SSH subprocess behind fixed node/action allow-lists. An admin-only FastAPI router normalizes bridge state, records explicit operations in PostgreSQL, and serves a React page that polls status without exposing credentials or raw command output.

**Tech Stack:** Python 3.11, FastAPI, Pydantic, SQLAlchemy 2, Alembic, PostgreSQL `company` schema, React 18, TypeScript, TanStack Query, Tailwind, shadcn/ui, Vitest, pytest, Tailscale CLI, systemd, OpenSSH

**Spec:** `docs/superpowers/specs/2026-09-03-forgehub-vpn-control-design.md`

## Global Constraints

- Tailscale remains independent from Cloudflare; no VPN code calls, reads, or configures Cloudflare.
- Do not change UFW, DNS, public listeners, Cloudflare, Tailscale ACLs, MagicDNS, routes, exit nodes, Serve, Funnel, or Tailscale SSH.
- Never return or persist auth URLs, auth keys, bridge tokens, private keys, SSH key paths, arbitrary commands, or raw subprocess output.
- Browser API routes require an authenticated administrator through `get_current_admin`.
- Bridge endpoints accept only logical node IDs and action enums; subprocesses use argv arrays, fixed timeouts, bounded output, and no shell.
- Resolve Tailscale IPs from live node identity; never hardcode `100.x` addresses and never fall back to a public IP.
- Local actions are `connect`, `disconnect`, `restart`, and `test`; remote actions are only `restart` and `test`.
- Status polling is read-only; every explicit operator action is audit-persisted.
- Do not modify firewall state during development implementation or smoke tests.

---

### Task 1: Build the pure Tailscale host adapter

**Files:**
- Create: `host-bridge/vpn_control.py`
- Create: `host-bridge/tests/test_vpn_control.py`

**Interfaces:**
- Consumes: fixed node names and an injected argv runner
- Produces: `parse_status(raw: str) -> dict`, `parse_ping(raw: str) -> dict`, `VpnControl.status() -> dict`, and `VpnControl.action(node: str, action: str) -> dict`

- [ ] **Step 1: Write failing parser and policy tests**

Create realistic `tailscale status --json` fixtures and assert:

```python
status = parse_status(json.dumps(RUNNING_DERP_STATUS))
assert status["local"]["hostname"] == "NotebookSTI-wsl"
assert status["remote"]["hostname"] == "vmi3547248"
assert status["connection"] == {"kind": "derp", "relay": "fra"}
assert status["remote"]["tailscale_ipv4"] == "100.105.235.114"
```

Add cases for direct `CurAddr`, idle, offline, `NeedsLogin`, absent peer, malformed JSON, IPv6 preceding IPv4, and unrelated peers. Test `parse_ping` against DERP, direct, and unrecognized output.

- [ ] **Step 2: Run tests and verify RED**

```bash
cd backend && .venv/bin/pytest ../host-bridge/tests/test_vpn_control.py -v
```

Expected: collection fails because the adapter does not exist.

- [ ] **Step 3: Implement pure parsing and policy**

Define:

```python
LOCAL_HOSTNAME = "NotebookSTI-wsl"
REMOTE_HOSTNAME = "vmi3547248"
ALLOWED_ACTIONS = {
    "local": frozenset({"connect", "disconnect", "restart", "test"}),
    "remote": frozenset({"restart", "test"}),
}
```

Select the local `Self` and only the peer matching `REMOTE_HOSTNAME`. Accept a Tailscale IPv4 only when `ipaddress.ip_address(value)` falls in `100.64.0.0/10`. Normalize only required fields; never return raw JSON.

- [ ] **Step 4: Implement injected execution and sanitization**

Use argv lists, fixed timeouts, an 8 KiB internal output bound, and stable error codes: `binary_missing`, `daemon_unavailable`, `needs_login`, `peer_offline`, `timeout`, `command_failed`, and `invalid_response`. Connect must use exactly:

```python
["tailscale", "up", "--hostname=NotebookSTI-wsl", "--accept-dns=false",
 "--accept-routes=false", "--advertise-exit-node=false", "--ssh=false"]
```

Strip one-time login URLs and all raw stdout/stderr from returned failures.

- [ ] **Step 5: Test exact safe commands**

Use a recording fake runner. Assert exact argv for every local action. Assert remote disconnect, unknown nodes, and unknown actions raise `VpnPolicyError` before execution. Assert a connection test runs:

```python
["tailscale", "ping", "--until-direct=false", "--c", "1", resolved_private_ip]
```

- [ ] **Step 6: Verify GREEN and commit**

```bash
cd backend && .venv/bin/pytest ../host-bridge/tests/test_vpn_control.py -v
git add ../host-bridge/vpn_control.py ../host-bridge/tests/test_vpn_control.py
git commit -m "VPN: add safe Tailscale adapter"
```

### Task 2: Expose guarded host-bridge endpoints

**Files:**
- Modify: `host-bridge/app.py`
- Modify: `host-bridge/vpn_control.py`
- Modify: `host-bridge/tests/test_vpn_control.py`

**Interfaces:**
- Consumes: Task 1 `VpnControl` and bridge-token authentication
- Produces: `GET /v1/vpn/status` and `POST /v1/vpn/nodes/{node}/actions`

- [ ] **Step 1: Write failing endpoint and remote-command tests**

Assert bridge-token rejection, request validation, exact remote SSH argv, private-IP-only resolution, strict host-key alias use, `BatchMode=yes`, and only `sudo -n systemctl restart tailscaled` after the SSH destination.

- [ ] **Step 2: Run focused tests and verify RED**

```bash
cd backend && .venv/bin/pytest ../host-bridge/tests/test_vpn_control.py -k 'endpoint or remote' -v
```

- [ ] **Step 3: Add host-only configuration**

Read `FORGEHUB_VPN_REMOTE_USER`, `FORGEHUB_VPN_REMOTE_KEY_PATH`, and `FORGEHUB_VPN_REMOTE_HOST_KEY_ALIAS` only from the host environment. Validate the real key path beneath the bridge's existing private-key roots and never return it.

- [ ] **Step 4: Implement remote private-Tailscale behavior**

Resolve the private IP immediately before each operation. Cache private-SSH posture for 30 seconds. For restart, dispatch the fixed command, then condition-poll local Tailscale status for at most 30 seconds until the peer is online. Do not use or return the public IP.

- [ ] **Step 5: Wire authenticated endpoints**

```python
@app.get("/v1/vpn/status")
async def vpn_status(x_bridge_token: str | None = Header(default=None)) -> dict:
    _check_token(x_bridge_token)
    return await asyncio.to_thread(_vpn_control.status)

@app.post("/v1/vpn/nodes/{node}/actions")
async def vpn_action(node: str, req: VpnActionRequest, x_bridge_token: str | None = Header(default=None)) -> dict:
    _check_token(x_bridge_token)
    return await asyncio.to_thread(_vpn_control.action, node, req.action)
```

Map invalid policy to 400, offline peer to 409, bounded command failure to 502, and timeout to 504, using sanitized details only.

- [ ] **Step 6: Verify and commit**

```bash
cd backend
.venv/bin/pytest ../host-bridge/tests/test_vpn_control.py -v
.venv/bin/python -m py_compile ../host-bridge/vpn_control.py ../host-bridge/app.py
git add ../host-bridge/app.py ../host-bridge/vpn_control.py ../host-bridge/tests/test_vpn_control.py
git commit -m "VPN: expose guarded host operations"
```

### Task 3: Add operation audit and admin API

**Files:**
- Create: `backend/app/db/models/vpn.py`
- Create: `backend/app/api/schemas/vpn.py`
- Create: `backend/app/api/routes/vpn.py`
- Create: `backend/alembic/versions/4e9d9c51a7b2_add_vpn_operation_events.py`
- Create: `backend/app/tests/test_vpn.py`
- Modify: `backend/app/db/models/__init__.py`
- Modify: `backend/app/main.py`

**Interfaces:**
- Consumes: Task 2 bridge endpoints, `get_current_admin`, and `get_db`
- Produces: `GET /api/v1/vpn/status`, `POST /api/v1/vpn/nodes/{node}/actions`, `GET /api/v1/vpn/operations`, and `VpnOperationEvent`

- [ ] **Step 1: Write failing authorization and response tests**

Mock bridge HTTP while testing the real FastAPI app. Assert admin success, non-admin 403, partial status as HTTP 200, `independent_from_cloudflare is True`, normalized nodes, and absence of secret/raw fields.

- [ ] **Step 2: Run tests and verify RED**

```bash
cd backend && .venv/bin/pytest app/tests/test_vpn.py -v
```

- [ ] **Step 3: Create audit model and migration**

Define `VpnOperationEvent(Base, TimestampMixin)` with UUID ID, nullable string-form FK `company.users.id`, constrained `target`, `action`, and `status`, `started_at`, nullable `completed_at`, bounded `result_code`, and bounded sanitized `summary`. Generate from head `f6d9a3b7c210`; inspect that upgrade creates only `company.vpn_operation_events` plus indexes and downgrade removes only them.

- [ ] **Step 4: Define explicit Pydantic schemas**

Create typed `VpnPosture`, `VpnNode`, `VpnConnection`, `VpnStatus`, `VpnActionRequest`, `VpnActionResult`, and `VpnOperationOut`. Use `Literal` enums and forbid extra action-request fields; do not expose a browser-facing `dict[str, Any]` contract.

- [ ] **Step 5: Implement admin routes and audit lifecycle**

Use `get_current_admin`, a bridge client timeout capped at 35 seconds, and internal `X-Bridge-Token`. Validate policy before bridge contact. Insert `running`, call bridge, then commit `succeeded` or `failed` even when returning 409/502/504. Clamp operation history to 1..100, default 25, newest first. Register the router without adding it to the bridge-token middleware bypass.

- [ ] **Step 6: Test policy and persistence**

Assert allowed actions, remote disconnect rejection before bridge contact, success/failure event transitions, newest-first bounded history, partial status, and sanitation of a mocked login URL/private path.

- [ ] **Step 7: Verify and commit**

```bash
cd backend
.venv/bin/pytest app/tests/test_vpn.py -v
.venv/bin/alembic heads
.venv/bin/ruff check app/api/routes/vpn.py app/api/schemas/vpn.py app/db/models/vpn.py app/tests/test_vpn.py
git add app/db/models/vpn.py app/api/schemas/vpn.py app/api/routes/vpn.py app/db/models/__init__.py app/main.py app/tests/test_vpn.py alembic/versions/*_add_vpn_operation_events.py
git commit -m "VPN: add audited admin API"
```

### Task 4: Add admin navigation and typed client hooks

**Files:**
- Create: `frontend/src/hooks/useVpn.ts`
- Modify: `frontend/src/components/layout/navSections.ts`
- Modify: `frontend/src/components/layout/Sidebar.tsx`
- Modify: `frontend/src/components/layout/CommandPalette.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/i18n/locales/pt-BR/common.json`
- Modify: `frontend/src/i18n/locales/en/common.json`
- Create: `frontend/src/components/layout/navSections.test.tsx`
- Create: `frontend/src/hooks/useVpn.test.tsx`

**Interfaces:**
- Consumes: Task 3 API and `user.is_admin`
- Produces: `useVpnStatus`, `useVpnOperations`, `useVpnAction`, sidebar/command-palette entry, and guarded `/vpn` route

- [ ] **Step 1: Write failing navigation tests**

Assert Operations includes `{to: "/vpn", labelKey: "nav.vpn", module: "vpn", adminOnly: true}`. Render sidebar and command palette as admin/non-admin; only admin may see/search VPN. Assert direct non-admin route navigation is rejected.

- [ ] **Step 2: Run the exact new test and verify RED**

```bash
cd frontend && npm test -- src/components/layout/navSections.test.tsx
```

- [ ] **Step 3: Implement explicit admin-only navigation**

Add `adminOnly?: boolean` to link/group types. Filter it in Sidebar and CommandPalette before rendering/search. Add a VPN link under Operations, Portuguese/English `nav.vpn`, and a `RequireAdmin` route wrapper in `App.tsx`.

- [ ] **Step 4: Write failing hook behavior tests**

Mock `apiClient`; prove 10-second visible-page polling, exact `{node, action}` request routing, and invalidation of `["vpn", "status"]` plus `["vpn", "operations"]` after success or failure.

- [ ] **Step 5: Implement typed TanStack Query hooks**

Mirror backend Literal unions. Poll status every 10 seconds only while visible with `retry: false`; load 25 operations; post to the fixed node action route; refresh status and audit history on settlement.

- [ ] **Step 6: Verify and commit**

```bash
cd frontend
npm test -- src/components/layout/navSections.test.tsx src/hooks/useVpn.test.tsx
git add src/hooks/useVpn.ts src/components/layout/navSections.ts src/components/layout/Sidebar.tsx src/components/layout/CommandPalette.tsx src/App.tsx src/i18n/locales/pt-BR/common.json src/i18n/locales/en/common.json src/components/layout/navSections.test.tsx src/hooks/useVpn.test.tsx
git commit -m "VPN: add admin navigation and client"
```

### Task 5: Build the resilient VPN page

**Files:**
- Create: `frontend/src/pages/vpn/index.tsx`
- Create: `frontend/src/pages/vpn/VpnNodeCard.tsx`
- Create: `frontend/src/pages/vpn/VpnTopology.tsx`
- Create: `frontend/src/pages/vpn/VpnOperations.tsx`
- Create: `frontend/src/pages/vpn/index.test.tsx`
- Create: `frontend/src/i18n/locales/pt-BR/vpn.json`
- Create: `frontend/src/i18n/locales/en/vpn.json`
- Modify: `frontend/src/i18n/index.ts`

**Interfaces:**
- Consumes: Task 4 hooks and DTOs
- Produces: responsive `/vpn` operations experience

- [ ] **Step 1: Load required UI guidance**

Invoke and follow `frontend-design-premium:frontend-design` together with `frontend-design-premium:frontend-design-premium`. Maintain project `DESIGN.md` exactly as directed. Invoke `superdesign:superdesign` if its canvas is callable and useful as an implementation reference; repo-native React/Tailwind remains the deliverable.

- [ ] **Step 2: Write failing page tests**

Assert both nodes, private IPs, direct/DERP/idle/offline/NeedsLogin states, “Tailscale independente do Cloudflare”, local four-action set, remote restart/test without disconnect, in-app confirmations, per-node action locking, stable loading/partial/error/history states, accessibility labels, and absence of secret/raw fields.

- [ ] **Step 3: Run page test and verify RED**

```bash
cd frontend && npm test -- src/pages/vpn/index.test.tsx
```

- [ ] **Step 4: Implement visual hierarchy and topology**

Build a header with freshness/manual refresh, a compact `NotebookSTI-wsl → direct/DERP → vmi3547248` strip, and equal-height node cards on desktop that stack on narrow screens. Combine semantic text with icons/colors so status never relies on color alone.

- [ ] **Step 5: Implement guarded actions and resilient states**

Use shadcn components and the existing `ConfirmDialog`, never native dialogs. Confirm local disconnect and all restarts. Keep test immediate. When remote is offline, explain provider-console recovery instead of rendering an unusable restart control.

- [ ] **Step 6: Implement recent operations**

Show actor, target, action, result, timestamps, and sanitized summary as a desktop table/mobile stack for the latest 25 entries, with manual refresh and no pagination in this MVP.

- [ ] **Step 7: Verify and commit**

```bash
cd frontend
npm test -- src/pages/vpn/index.test.tsx src/components/layout/navSections.test.tsx src/hooks/useVpn.test.tsx
npm run build
git add src/pages/vpn src/i18n/index.ts src/i18n/locales/pt-BR/vpn.json src/i18n/locales/en/vpn.json
git commit -m "VPN: build operations dashboard"
```

### Task 6: Integrate, migrate, document, and smoke-test

**Files:**
- Create: `docs/screens/vpn.md`
- Create: `docs/guides/VPS_TAILSCALE_OPERATIONS.md`
- Modify: `docs/superpowers/specs/2026-09-03-forgehub-vpn-control-design.md`

**Interfaces:**
- Consumes: Tasks 1–5
- Produces: migrated dev environment, verified live `/vpn`, and operational documentation

- [ ] **Step 1: Run focused automated verification**

```bash
cd backend
.venv/bin/pytest ../host-bridge/tests/test_vpn_control.py app/tests/test_vpn.py -v
.venv/bin/ruff check app/api/routes/vpn.py app/api/schemas/vpn.py app/db/models/vpn.py app/tests/test_vpn.py
cd ../frontend
npm test -- src/pages/vpn/index.test.tsx src/components/layout/navSections.test.tsx src/hooks/useVpn.test.tsx
npm run build
```

- [ ] **Step 2: Apply and verify migration**

```bash
cd backend
.venv/bin/alembic current
.venv/bin/alembic upgrade head
.venv/bin/alembic current
```

Expected: current equals the single head and `company.vpn_operation_events` exists.

- [ ] **Step 3: Restart canonical dev services**

```bash
cd /root/project/forgehub
./dev.sh restart
./dev.sh status
curl -fsS http://localhost:8001/health
curl -fsS -o /dev/null -w '%{http_code}\n' http://localhost:5172
```

- [ ] **Step 4: Run safe live API and browser smoke checks**

As admin, load status/history and run only non-disruptive `test`. Confirm two dynamically resolved nodes, current direct/DERP path, one sanitized audit event, sidebar/command-palette discovery, responsive layout, keyboard focus, and no browser console/network errors. Confirm non-admin navigation is hidden and API access returns 403.

- [ ] **Step 5: Document verified behavior**

Document the screen, data flow, allow-list, partial failures, out-of-band recovery, and Tailscale's independence from Cloudflare. Mark the spec `Implemented and verified` only after all evidence passes.

- [ ] **Step 6: Verify docs and commit**

```bash
rg -n 'TBD|TODO|PLACEHOLDER|tailscale.*through Cloudflare|remote.*disconnect' docs/screens/vpn.md docs/guides/VPS_TAILSCALE_OPERATIONS.md docs/superpowers/specs/2026-09-03-forgehub-vpn-control-design.md
git diff --check
git status --short
git add docs/screens/vpn.md docs/guides/VPS_TAILSCALE_OPERATIONS.md docs/superpowers/specs/2026-09-03-forgehub-vpn-control-design.md
git commit -m "VPN: document verified operations"
```

- [ ] **Step 7: Complete verification and branch handoff**

Invoke `superpowers:verification-before-completion`, rerun its required checks, then invoke `superpowers:finishing-a-development-branch`. Do not close firewall ports or modify Cloudflare during branch completion.
