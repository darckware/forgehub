# Windows Remote Desktop Setup Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a Windows system script that enables Remote Desktop only after customer authorization, informs the active workstation user, grants the explicitly selected local support user access, and restricts inbound TCP 3389 to the Tailscale network.

**Architecture:** Add one idempotent PowerShell system script to `backend/app/core/system_scripts.py`, seeded into the existing Acesso Remoto category. The ForgeHub operator records the customer's authorization as a required run parameter; the script notifies the active Windows session before changing settings and fails closed if authorization, the session, or notification is missing.

**Tech Stack:** Python, PowerShell 5.1, FastAPI system-script catalog, pytest.

**Spec:** User request in this conversation; `backend/app/core/host_enrollment.py` defines the established support login `darckware`; `backend/app/core/host_preparation.py` defines `TAILNET_CIDR = "100.64.0.0/10"`.

## Global Constraints

- Require the operator to set `CLIENTE_AUTORIZOU=sim`; the default is `nao` and must cause an exit before any machine setting changes.
- Send a notice to the active Windows user before enabling RDP; if there is no active user or `msg.exe` cannot deliver the notice, make no changes.
- Require the operator to enter the support username (`USUARIO_SUPORTE`); accept only an existing, enabled local account. Never create a replacement account or change its password. This supports the user's request to choose the user who receives RDP access.
- Enable Remote Desktop with Network Level Authentication and TCP port 3389.
- Create a dedicated inbound firewall allow rule restricted to `100.64.0.0/10`; do not enable a built-in broad Remote Desktop rule.
- Read the effective `ActiveStore` firewall policy; require Windows Firewall enabled and inbound default not `Allow`; reject conflicting inbound block rules for TCP/3389.
- Detect an already-enabled broad TCP 3389 rule, including GPO rules, and stop rather than silently widening or disabling unrelated policy.
- Resolve the support account by literal equality and require exactly one enabled local account; refuse an existing RDP port other than 3389 before any changes.
- Verify the effective firewall rule is enabled and tailnet-scoped, and verify the TCP/3389 listener belongs to `TermService`.
- Independently review the final script's authorization ordering and firewall scope before considering the work complete.

## Review Focus

1. Missing or negative customer authorization must exit before registry, service, group, or firewall writes.
2. A missing interactive session or failed notice must exit before any RDP change.
3. A missing or ambiguous local account must stop without creating an account or granting access.
4. An enabled broad inbound rule for TCP 3389 in ActiveStore must be reported and block activation.
5. Disabled firewall profiles, inbound default `Allow`, or an active 3389 block rule must stop before mutation.
6. The ForgeHub firewall rule must be effective and allow TCP 3389 only from `100.64.0.0/10`.
7. A wildcard/ambiguous username or existing RDP port other than 3389 must stop before mutation.
8. Success requires the listening PID to match TermService.

## Task 1: Add script regression tests

**Files:**
- Test: `backend/app/tests/test_system_rdp_script.py`.

- [x] **Step 1: Add a failing test** for the `rdp_setup:windows` catalog entry, asserting its name/category, default-deny authorization parameter, explicit support user, notice-before-change order, NLA, port 3389, and Tailscale-only rule.
- [x] **Step 2: Run the focused test with the test conftest disabled** and confirm it fails because the system script does not exist (`StopIteration`).
- [x] **Step 3: Add regression assertions** for refusal paths and mutation order: no authorization, failed notice, missing/ambiguous support account, broad ActiveStore rule, disabled firewall/default allow, and custom existing RDP port.
- [x] **Step 4: Confirm the static catalog test passes after implementation.** A Windows PowerShell runtime is not available in this environment.

## Task 2: Implement the Windows system script

**Files:**
- Modify: `backend/app/core/system_scripts.py`.
- Test: `backend/app/tests/test_system_rdp_script.py`.

- [x] Add the Windows entry `rdp_setup:windows` under `acesso_remoto`, with required `CLIENTE_AUTORIZOU` options `nao`/`sim`, default `nao`, required `USUARIO_SUPORTE`, and timeout suitable for validation.
- [x] Check administrator rights and authorization first; use `msg.exe *` to notify interactive sessions and fail before changes if delivery fails.
- [x] Validate the literal local account, effective firewall profiles/rules, and current RDP port before notification or changes.
- [x] Enable RDP/NLA and TermService, add that account to the local Remote Desktop Users group, and create the Tailscale-scoped firewall rule.
- [x] Make repeat runs idempotent and print verified final service, registry, group, listener PID, and effective ActiveStore firewall state without exposing credentials.
- [x] Add the script to the Windows Ações menu and keep it hidden for non-Windows hosts.
- [x] Run `PYTHONPATH=backend python -m pytest --noconftest backend/app/tests/test_system_rdp_script.py -q` (1 passed), frontend system-action tests, locale check, frontend build, Ruff, and `git diff --check`.

## Task 3: Independent security review and reporting

**Files:**
- Review: `backend/app/core/system_scripts.py` and `backend/app/tests/test_system_rdp_script.py`.

- [x] Obtain a separate review of the script's mutation order, quoting, idempotency, user notification, and effective firewall scope.
- [x] Resolve the Important findings on ActiveStore/GPO, profile defaults/blocks, wildcard lookup, non-3389 existing port, final listener identity, and mutation-order test coverage.
- [x] Complete the independent re-review and record remaining limitations; PowerShell/Windows runtime execution remains unavailable.
- [ ] Do not commit or deploy under this plan.
