# Maintenance Work and Remote Access Control Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Keep the checkboxes and checkpoint log current.

**Goal:** Finish the agent-work queue separation and maintenance checklist, add a controlled Windows RDP setup action, and fix host editing in Remote Access.

**Architecture:** Keep message classification as the source of truth. Route each human action to its owning Personal tab; keep RDP configuration in the seeded Windows system-script catalog. The maintenance queue work and RDP script are separate workstreams, detailed in the linked plans below.

**Tech Stack:** FastAPI, SQLAlchemy, React, TypeScript, Vitest, pytest, Windows PowerShell.

**Spec:** [Agent-work queue plan](./2026-11-16-maintenance-demand-validation.md); [Windows RDP plan](./2026-11-16-windows-rdp-setup.md); `docs/superpowers/specs/2026-11-08-messages-triage.md`.

## Global Constraints

- Work only in `/root/project/forgehub/.claude/worktrees/agent-work-decisions`.
- Keep changes surgical and report only checks actually run.
- Backend tests must use the isolated test environment; never use the production database.
- RDP firewall access must be limited to Tailscale `100.64.0.0/10`.
- Obtain and record the client's authorization before enabling RDP; notify an active workstation user before changing settings.
- No commit, push, merge, or deploy without Marcelo's explicit approval of the exact content.

## Review Focus

1. A correction or uncertain execution links to Decisões, never Aprovações. Cover with routing and label tests.
2. An authorization remains in Aprovações, a blocking question in Respostas, and an incubation in Incubações. Cover all four routes in `messageLabels.test.ts` and the demands-page tests.
3. A maintenance item appears once in its owning Personal queue, with a count matching the list. Cover with backend view tests and the end-to-end checklist.
4. Cancelling a decision confirmation must not change or dispatch the demand. Cover with the existing confirmation test and checklist.
5. RDP must not be enabled without recorded client authorization, a deliverable user notice, the `darckware` account, and a tailnet-only firewall rule. Cover with system-script tests.

## Progress Register

| Workstream | Status | Evidence / next checkpoint |
|---|---|---|
| Personal tabs and disjoint backend queues | Implemented; focused verification passed | `AgentTasksTab.test.tsx`: 47 passed; focused backend tests: 2 passed; isolated SQL predicate test: 1 passed. Next: final route and checklist acceptance. |
| Messages-to-Personal destination | Verified | Correction/reconciliation now route to Decisões and the link label uses the same classification. `messageLabels.test.ts` plus `demands/index.test.tsx`: 12 passed. |
| Maintenance execution/correction checklist | Verified | Runbook created; five focused frontend files: 91 passed; backend pure queue predicate and RDP catalog tests: 2 passed; earlier isolated DB view tests: 2 passed. Build and locale check passed. Production actions were not run. |
| Windows RDP setup | Verified (static + independent re-review) | Single `ActiveStore` query + in-memory filtering, WTS active-session `msg.exe` delivery, CIDR + dotted-quad mask parsing, `PersistentStore` parity, NLA-before-enable ordering, and strict per-branch refusal assertions. `test_system_rdp_script.py`: 1 passed; Ruff passed; independent read-only re-review (`rdp_security_reviewer`) returned `STATUS: DONE` with 0 Critical/Important findings. PowerShell/Windows runtime remains unavailable here. |
| Remote Access host editing | Verified (unit/API) | Labels updated (`Nome do host` / `Host name` / `Nombre del host`); `ServerForm` sends minimal `buildServerUpdate` diff and relaxes edit schema only for pre-empty `ip_address`/`remote_user` so unprepared tailnet/enrolled hosts can be renamed; `update_server` strips/validates `name` and reports `409 Host '...' already exists` instead of tailnet-link error; `ServerForm` surfaces safe backend errors via `apiErrorText` while keeping unsaved input. `test_server_edit.py` (1 passed), 5 frontend files (95 passed), `i18n:check`, and build passed. 390/1440 px browser check unavailable in sandbox. |
| Responsive browser check | Blocked in prior attempt | 390/1440 px check was not completed because the sandbox refused the local preview listener. Retry only if a permitted preview/browser path is available. |
| Commit/deploy | Not authorized | Do not commit, push, or deploy under this plan. |

## Execution Order

- [x] Separate the Personal work queues and backend views; focused verification is recorded below.
- [x] Fix message routing and labels for correction decisions; prove route and label together.
- [x] Complete [maintenance-demand validation](./2026-11-16-maintenance-demand-validation.md): prove the maintenance workflow and create its operator checklist.
- [x] Complete [Windows RDP setup](./2026-11-16-windows-rdp-setup.md): add the guarded script and obtain an independent security review.
- [x] Complete [Remote Access host editing](./2026-11-16-remote-access-host-edit.md): rename the field to “Nome do host”, reproduce and fix the save failure, and verify name-only edits preserve access data.
- [x] Run final focused verification and update this register with evidence and any remaining blockers.
- [ ] Report remaining blockers; request exact-content approval only if a later commit or deployment is requested.

## Checkpoint Contract

After each workstream, record its status, changed artifact(s), exact checks and result, unresolved issue, and the next action in this file before starting another workstream. Use `Pending`, `In progress`, `Verified`, or `Blocked` consistently. This register is the restart point if work is interrupted; do not repeat a `Verified` item unless later changes invalidate its evidence.

## Checkpoint Log

- **2026-11-16 — Queue separation:** the five-tab UI and backend queue separation are present in the worktree. Focused frontend tests, backend predicate test, two isolated DB tests, locale check, build, and `git diff --check` passed. Build reported existing large-chunk/Mermaid warnings. Strict UI audit found 59 repository findings and none in the changed Personal surface.
- **2026-11-16 — Routing diagnosis:** screenshot item `#42246` is a correction decision. `operatorDestination()` currently sends all `agent_tasks` to Aprovações; no routing fix has been applied yet.
- **2026-11-16 — Messages routing:** added a failing test for `correction`/`reconciliation`, then routed those decisions to Decisões and derived the link label from the same destination classification. `messageLabels.test.ts` + `demands/index.test.tsx`: 12 passed; authorization, question, incubation, and Moodle paths remain covered. Next: write the operator checklist and verify the queue workflow. No commit, push, merge, or deploy has been performed.
- **2026-11-16 — Host edit added to scope:** screenshot identifies the shared `ServerForm` used by Acesso Remoto. The field is currently localized as “Nome do servidor”; the form sends a PUT and displays a generic save error, so the actual API rejection still needs reproduction. Dedicated plan added; no host edit code changed yet.
- **2026-11-16 — Maintenance workflow:** operator runbook created at `docs/runbooks/maintenance-demand-validation-checklist.md`; it records expected queue routes, exclusivity/count checks, confirmation/cancellation behavior, evidence fields, and restart point. Frontend queue/routing tests: 91 passed; backend predicate + RDP catalog tests: 2 passed; prior isolated DB queue tests: 2 passed. Locale check, frontend build, Ruff, and `git diff --check` passed. Browser viewport check remains unavailable.
- **2026-11-16 — RDP independent review and fixes:** first review found Important gaps in ActiveStore/GPO checks, firewall defaults and block rules, literal account lookup, existing custom port handling, and final listener ownership. The script now checks those conditions before mutation and validates effective state after; focused static test passes. Re-review requested; no Windows PowerShell runtime is available here.
- **2026-11-16 — RDP re-review and closure:** addressed remaining re-review findings: `ActiveStore` single-query in-memory filtering (`CmdletizationQuery_NotFound` guard), WTS active-session enumeration for `msg.exe` under `$ErrorActionPreference = 'Continue'` try/finally, `Get-IPv4Range` CIDR + dotted-quad subnet mask parsing, `PersistentStore` parity on `$ownedRules`, `UserAuthentication = 1` before `fDenyTSConnections = 0`, and strict per-branch refusal assertions in `test_system_rdp_script.py`. Independent read-only re-review (`rdp_security_reviewer`) returned `STATUS: DONE` with 0 Critical/Important findings; `test_system_rdp_script.py` (1 passed) and Ruff passed. Windows PowerShell runtime remains unavailable here.
- **2026-11-16 — Remote Access host editing:** reproduced `PUT /api/v1/servers/{id}` returning `409 This tailnet device is already linked to another machine` on duplicate host names, and identified `ServerForm` sending full-record payloads / requiring non-empty `remote_user` and `ip_address` (blocking tailnet-synced/enrolled hosts) while masking errors behind `form.saveFailed`. Updated `update_server` to validate/strip `name` and return `409 Host '...' already exists` (plus `422` on blank fields), updated `ServerForm` + `useServers.ts` to send minimal diffs (`buildServerUpdate`) and surface safe `apiErrorText` details while preserving unsaved input, and renamed `servers.form.name` to `Nome do host` / `Host name` / `Nombre del host`. Verified with `test_server_edit.py` (1 passed), focused backend suite (26 passed), 5 frontend files (95 passed), `i18n:check`, Ruff, `npm run build`, and `git diff --check`. No commit, push, merge, or deploy was performed.
