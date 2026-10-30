# M0.SPEC — Minimal Mission: contracts, model, guards and MCP tools

**Status:** proposed specification for review (M0.SPEC, Plano Integrado Onda 1). Not implemented.
**Author:** Porthus. **Reviewers:** Dartan (first), Aegis (second). **Consulted:** Daedalus (read-only).
**Date:** 2026-10-29. **Base commit read:** `develop` @ `dcfe941`.
**Language:** English per decision D-5 (technical spec/API in English; business brief in pt-BR).

This specification is the authoritative contract for M0.0, M0.6a, M0.6b, M0.2a–d, the minimal
mission executions screen (decided 2026-10-29) and the orchestrator decision cycle (decided
2026-10-29). Nothing written here exists until an implementation slice ships it with tests.

## Index

| Document | Covers |
|---|---|
| This file | §0 conventions · §1 inventory (existing × proposed) · §2 M0.0 model and migration · §3 state projection · §4 guards M0.6a/M0.6b · §5 MCP tool contracts (M0.2a–d) · §6 minimal context allowlist · §7 plan submission · §8 minimal formal acceptance · §9 planned tests · §10 deferred to M.1 · §11 open decisions · §12 what was not verified |
| [MISSION_EXECUTIONS_SCREEN_SPEC.md](MISSION_EXECUTIONS_SCREEN_SPEC.md) | Minimal mission executions screen: routes, execution state model, conflicts, environments, actions, permissions, loading/empty/error, 390/1440 px, tests |
| [MISSION_ORCHESTRATOR_CYCLE_SPEC.md](MISSION_ORCHESTRATOR_CYCLE_SPEC.md) | Orchestrator decision cycle via Operação 24x7 (actions, N0–N3 limits, decision record, gates, undo/lock) and multiple missions (priority, per-orchestrator limit, inter-mission dependency, listing/filtering) |

Source documents: `docs/plano-integrado/04-missao-pipeline-e-papeis.md` (states, roles, §6–§7),
`07-fases-de-implementacao.md` (M0 row), `12-primeira-onda.md` §4/§5/§6, `09-lacunas-e-decisoes.md`
(D-1…D-8, 2026-10-29 decisions), `08-inteligencia-operacional.md` (N0–N3).

Mapping of `12-primeira-onda.md` §4 checklist to this spec:

| §4 item | Section |
|---|---|
| Inventory/reuse `project.py`, `task.py`, `governance.py`, `orchestration.py`, `factory_server.py`; existing vs proposed | §1 |
| Per tool: input/output, actor/scope, HTTP status and MCP error, idempotency key and conflict, audit, limit/timeout, rollback | §5 (and §0.3–§0.6 for shared rules) |
| `project_type=mission` as planned migration + 04 state projection; preserve creation/maintenance, `ProjectAgentMembership`, `TaskExecutionReview` | §2, §3 |
| Minimal context by allowlist, no broad retrieval before C.2b; canaries; simulated runner and test `agt_` | §6, §9.6 |
| `submit_project_plan` only submits; approval/baseline on screen by authorized user; no approver token in the tool | §7 |
| Common guards M0.6a/b: hash/ids, replay, revoked permission, uncertain cancellation, rollback | §4 |
| Minimal formal acceptance (12 "Aceite mínimo persistido da M0") | §8 |
| Executions screen (29/10) | screen spec |
| Orchestrator decision cycle and multiple missions (04 §6–§7) | cycle spec |

---

## 0. Conventions used by every contract

### 0.1 Labels

- **[EXISTS file:line]** — verified in `develop@dcfe941` by reading the code; the line is the
  decorator or definition.
- **[PROPOSED]** — does not exist; to be built by the slice named next to it.
- **[EXTEND file:line]** — existing code that the named slice changes.

### 0.2 Identities and authorization

- Agents call with their own `agt_` `AgentServiceCredential` (`FORGEHUB_AGENT_TOKEN`), resolved by
  `get_actor_principal` [EXISTS backend/app/core/deps.py:29] and authorized by `authorize_action`
  [EXISTS backend/app/core/deps.py:59] against an `AuthorityDelegation`
  [EXISTS backend/app/db/models/governance.py:221] scoped to the mission project. Deny by default.
- Humans call with JWT. In M0 every human write on a mission requires `is_admin` (Marcelo) except
  where noted; `authorize_action` already returns `("admin", None)` for admins.
- No shared bridge token (`X-Bridge-Token`) for any mission write. No borrowed credential. Missing or
  invalid `agt_` is a blocker the tool surfaces, never a fallback (12 §6).
- `RequireAuthMiddleware` only admits `agt_` on listed prefixes [EXISTS backend/app/main.py:200-232].
  Today an `agt_` caller reaches `GET /api/v1/projects|tasks|planning-items` and `PATCH /api/v1/tasks/*`
  only. **Finding:** `POST /api/v1/tasks` and `POST /api/v1/planning-items` are not on that list, so
  the existing MCP tools `create_project_task` / `create_planning_item`
  [EXISTS backend/app/mcp/factory_server.py:371,391] should be refused 401 for an `agt_`-only caller
  (code reading, not run — §12). M0.2a adds the prefix `/api/v1/missions/` [EXISTS since M0.0; M0.2a moved the list into `is_agent_command_path` in backend/app/main.py and tightened it to `/api/v1/missions` and `/api/v1/missions/...`] and the exact task
  sub-paths listed in §5 (M0.2c) to the `agt_` admission list [EXTEND backend/app/main.py:200]; each route
  still calls `authorize_action` itself.

New delegation action keys [PROPOSED, M0.2a], all project-scoped, `max_risk` respected:

| Action key | Grants | Typical grantee |
|---|---|---|
| `mission.manage` | create the mission project, manage members/links | orchestrator (Athos) |
| `mission.plan.submit` | submit a plan for approval (never approve) | orchestrator, planner |
| `planning.execution.manage` | **exists** (used by `backend/app/api/routes/task.py:149`); M0 reuses it for assign, dependency, dispatch | orchestrator |
| `mission.orchestrate` | decision-cycle actions (schedule, reassign, request review, return for correction, propose pause) | orchestrator |
| `mission.execution.report` | report an execution of a task **assigned to the caller** | executors |
| `mission.accept` | reserved; **refused in M0** (first mission is accepted by Marcelo only, 04 "Aceite mínimo M0") | — |

### 0.3 Error contract (HTTP → MCP)

All new routes return `detail` as an object `{ "code": "<UPPER_SNAKE>", "message": "<pt-BR or en text>", ...context }`.
The MCP keeps the existing `FactoryError` surface [EXISTS backend/app/mcp/factory_server.py:49,65-92]
and formats it as `ForgeHub <METHOD> <path> failed (<status>): <code>: <message>`. Existing routes keep
their string `detail`; a guard added to an existing route uses the object form.

| HTTP | Meaning | MCP behavior |
|---|---|---|
| 400 | malformed input | tool error, no retry |
| 401 | missing/invalid/expired/revoked `agt_` | tool error `UNAUTHENTICATED`, no retry, no fallback credential |
| 403 | no delegation / not a member / separation of duties | tool error, no retry |
| 404 | not found **or not visible to the caller** (no existence leak across projects) | tool error |
| 409 | guard refusal or idempotency conflict (`code` says which) | tool error; caller fixes cause |
| 422 | semantic validation | tool error |
| 502/504 | upstream (host-bridge) outcome uncertain | tool error `UPSTREAM_UNCERTAIN`; **never auto-retried**; reconcile first |

Timeout: the MCP client uses 30 s [EXISTS backend/app/mcp/factory_server.py:72]. A timeout on a write is reported as
`UPSTREAM_UNCERTAIN`; the caller must re-read state (or replay the same idempotency key, §0.4), never
issue a different write.

### 0.4 Idempotency

Every write tool takes a required `idempotency_key` (1–150 chars, caller-generated, e.g.
`<agent>-<task>-<purpose>-<uuid4>`). The server stores receipts in **[EXISTS M0.2a: backend/app/db/models/command_receipt.py, migration `d3f7a1c9e2b5`; helper `begin_command`/`record_command` in backend/app/core/command_receipts.py] table
`company.agent_command_receipts`**:

| Column | Type | Note |
|---|---|---|
| id | UUID PK (python default) | |
| principal_type, principal_id | String(20), UUID | who called |
| idempotency_key | String(150) | |
| command | String(80) | e.g. `mission.dispatch_task` |
| request_hash | String(64) | sha256 of canonical JSON of the request body |
| response_status | Integer | |
| response_body | JSONB | |
| target_type, target_id | String(50), UUID nullable | for audit joins |
| created_at/updated_at | TimestampMixin | |

`UNIQUE (principal_type, principal_id, idempotency_key)`. Same key + same hash → the stored response is
returned (HTTP 200 with header `Idempotent-Replay: true`). Same key + different hash → 409
`IDEMPOTENCY_KEY_REUSED`. Receipts are written in the same transaction as the effect. Retention 30 days
(swept by the existing retention loop pattern [EXISTS M0.2a: `run_command_receipt_retention`, loop `command-receipt-retention` in backend/app/main.py]). Where a natural key exists
(e.g. a membership `(project_id, agent_id)` already has `UNIQUE` [EXISTS orchestration.py model,
backend/app/db/models/orchestration.py:166-167]) it is checked as well.

Dispatch has a stronger rule: it **never** produces a second run for the same task while a previous
one is active, reserved or uncertain — this reuses `reserve_dispatch`
[EXISTS backend/app/core/demand_dispatch_guard.py:13] and the uncertain-run short-circuit in
`_dispatch_task_by_id` [EXISTS backend/app/api/routes/task.py:969 (block at 997-1019)].

### 0.5 Audit

Every mission write appends an `AuditEvent` [EXISTS backend/app/db/models/governance.py:108] with:
`entity_type` (`project`, `project_task`, `task_execution`, `mission`), `entity_id`, `event_type`
(names below), `actor` = authenticated display name (**never** `"system"` or `"forgehub"` for an act
of an agent or person — 04 §2), and `payload` with at least
`{principal_type, principal_id, authority_source, delegation_id, idempotency_key, reason?}`.
**Finding (fixed by M0.6a):** today `update_task` audits completion as `actor="system"`
[backend/app/api/routes/task.py:436-444] and `dispatch_task` as `actor="forgehub"` [backend/app/api/routes/task.py:1161-1167].

### 0.6 Rollback convention

Each slice ships: an Alembic migration with a working `downgrade()` tested up/down on the isolated
test database (T.1); a feature switch `MISSION_TOOLS_ENABLED` [EXISTS M0.2a, `core/config.py`, default
`false`; in M0.2a it gates the M0.2a contract only — `POST /missions` with an `idempotency_key` or a non-mission type, and `members:apply` — so the M0.0 routes keep working] that makes the new MCP tools and `/api/v1/missions/*` writes return 503
`MISSION_TOOLS_DISABLED` without touching data; guards are **not** switchable (disabling a guard is a
code rollback through the deploy gate, never a flag). Rolling back never deletes executions, reviews,
receipts or audit rows.

---

## 1. Inventory: existing × proposed

### 1.1 Existing, reused as-is or extended

| Capability | Where | Use in M0 |
|---|---|---|
| Project CRUD | `POST/GET/PATCH/DELETE /api/v1/projects` [EXISTS backend/app/api/routes/project.py:142,161,167,172,208] | mission is a Project; PATCH gains the mission guard (§3) |
| `PROJECT_TYPES = ("creation","maintenance")`, CHECK `ck_projects_project_type` | [EXISTS backend/app/db/models/project.py:67,100] | M0.0 adds `mission` |
| `ProjectCreate` does **not** expose `project_type` | [EXISTS backend/app/api/schemas/project.py:26-55] | kept; missions are created only through §5.1 |
| ProjectPlan CRUD + approve | [EXISTS backend/app/api/routes/project.py:219,233,246,251,282,296] | approve (`:282`) has **no** authorization beyond login; M0.6b refuses it for mission projects (§7) |
| PlanBaseline create/list/get | [EXISTS backend/app/api/routes/project.py:306,347,361]; model [EXISTS backend/app/db/models/project.py:229] | snapshot only of plan text/cost/date; M0.6b adds per-task items + hashes |
| ChangeRequest CRUD | [EXISTS backend/app/api/routes/project.py:374,424,437,461,522]; model [EXISTS backend/app/db/models/project.py:263] | the only way to change a baselined mission task |
| Task CRUD, `TASK_STATUSES` | [EXISTS backend/app/api/routes/task.py:303,338,380,388,456]; [EXISTS backend/app/db/models/task.py:44] | PATCH gains M0.6a/b guards |
| `_authorize_agent_task_update` (`planning.execution.manage` for `agt_`) | [EXISTS backend/app/api/routes/task.py:110] | reused |
| `_ensure_evidence_verified` (only `done`, only if executions exist) | [EXISTS backend/app/api/routes/task.py:488] | replaced by the global M0.6a guard |
| Executions create/list/get/patch | [EXISTS backend/app/api/routes/task.py:543,609,622,632] | `report_task_execution` builds on it |
| Dependencies with cycle check (advisory lock) | [EXISTS backend/app/api/routes/task.py:708,745,756] | `add_task_dependency` wraps `:708` |
| Assignments | [EXISTS backend/app/api/routes/task.py:807,853] | `assign_task` wraps `:807` |
| Task dispatch via Messages | [EXISTS backend/app/api/routes/task.py:946 → `_dispatch_task_by_id` :969] | `dispatch_task` tool wraps it; guards added |
| Memberships | `POST/GET /orchestration/projects/{id}/memberships`, `GET /orchestration/agents/{id}/memberships`, `PATCH /orchestration/memberships/{id}` [EXISTS backend/app/api/routes/orchestration.py:230,255,270,286] | `manage_project_members` wraps them; R.1 must preserve |
| Eligible memberships | [EXISTS backend/app/api/routes/orchestration.py:410] | reassign eligibility |
| Reviews | `POST/GET /orchestration/executions/{id}/reviews`, `PATCH /orchestration/reviews/{id}` [EXISTS backend/app/api/routes/orchestration.py:452,481,496] | independent review = `TaskExecutionReview` [EXISTS backend/app/db/models/orchestration.py:216] |
| Review dispatch (work-package only) | [EXISTS backend/app/api/routes/orchestration.py:640] | **not** usable for Messages executions (409 without work package); M0 uses §5.11 |
| Legacy direct dispatch | [EXISTS backend/app/api/routes/orchestration.py:565] returns 410 | untouched |
| Governed approval requests (hash-bound, idempotent decisions) | `GET /governed/approval-requests[/{id}]`, `POST /governed/approval-requests/{id}:decide` [EXISTS backend/app/api/routes/governed_approval.py:40,52,64]; models `ApprovalRequest`, `ApprovalDecisionRecord` [EXISTS backend/app/db/models/governance.py:187,246] | plan approval (§7) and mission acceptance (§8) add target types to `:decide` |
| Delegations | `GET/POST /governed/authority-delegations`, `:revoke` [EXISTS backend/app/api/routes/governed_approval.py:104,114,154] | mission delegations |
| Legacy approvals | `/governance/approvals*` [EXISTS backend/app/api/routes/governance.py:52,89,107,115,123]; approving a `project_task` auto-dispatches [EXISTS backend/app/api/routes/governance.py:180] | auto-dispatch must pass M0.6b (it does, via `reserve_dispatch`); legacy approvals are **not** a plan/acceptance path for missions |
| Audit events read | [EXISTS backend/app/api/routes/governance.py:234,252] | mission timeline source |
| Evidence verification `file:`/`git:`/`db:` | [EXISTS backend/app/core/task_evidence.py:78,99,126,140,164] | reused by M0.6a |
| Messages dispatch choke point | `_execute_dispatch` → `reserve_dispatch` [EXISTS backend/app/api/routes/demand.py:1462,1497; backend/app/core/demand_dispatch_guard.py:13] | M0.6b baseline guard and target serialization go here |
| Scheduled dispatch | `run_scheduled_dispatch_pass` [EXISTS backend/app/api/routes/demand.py:1854], `wake_scheduled_dispatch` [EXISTS backend/app/core/dispatch_signal.py:18] | `scheduled_at` scheduling (cycle spec) |
| Operator decisions on messages | `POST /demands/{id}/decision` [EXISTS backend/app/api/routes/demand.py:1190] → `decide_demand` [EXISTS backend/app/core/demand_workflow.py:95]; bulk [EXISTS backend/app/api/routes/demand.py:856] | reused for uncertain-run resolution |
| Agent work list | `GET /demands/agent-work` [EXISTS backend/app/api/routes/demand.py:843] (`WORK_VIEWS` [EXISTS backend/app/core/demand_management.py:9]) | screen reuses per execution |
| Message history | `GET /demands/{id}/history` [EXISTS backend/app/api/routes/demand.py:1199] | screen drill-down |
| Agent activity | `GET /agent-activity`, `/stream`, `/timeline`, `/snapshot` [EXISTS backend/app/api/routes/agent_activity.py:179,250,295,324] | screen: live state of executors |
| DocLink | `GET/POST/DELETE /api/v1/docs/links`, `GET /docs/links/by-entity` [EXISTS backend/app/api/routes/docs.py:375,385,401,434] | `attach_project_document` |
| Artifacts | `POST/GET /api/v1/artifacts`, versions [EXISTS backend/app/api/routes/artifact.py:110,153,169,233,292,329] | brief/dossier as versioned artifact |
| Routines (Operação 24x7) | `/operations/routines*` [EXISTS backend/app/api/routes/operations.py:749,760,779,807,816]; `run_routine_generation_pass` [EXISTS backend/app/api/routes/operations.py:239] | cycle trigger (cycle spec) |
| Agent questions (ask Marcelo, blocking) | `POST/GET /operations/agent-questions` [EXISTS backend/app/api/routes/operations.py:1004,1053]; MCP `ask_marcelo` [EXISTS host-bridge/forgehub_messages_mcp.py:625] | cycle "ask Marcelo" |
| Existing MCP factory tools | `list_projects`, `get_project_context`, `list_planning_items`, `list_project_tasks`, `update_task_status`, `report_governance_blocker`, `create_planning_item`, `create_project_task`, `release_planning_for_execution`, … [EXISTS backend/app/mcp/factory_server.py:107-442] | kept; `update_task_status` becomes subject to M0.6a |

### 1.2 Proposed (none of these exist)

| Item | Kind | Slice |
|---|---|---|
| `project_type='mission'` | migration (CHECK) | M0.0 |
| `company.project_missions` | table | M0.0 |
| `company.mission_project_links` | table | M0.0 |
| `company.mission_acceptance_criteria`, `company.mission_criterion_tasks` | tables | M0.0 |
| `company.plan_baseline_items`; `plan_baselines.content_hash`, `plan_baselines.superseded_at` | table + columns | M0.6b |
| `company.task_execution_targets` | table | M0.6b (target serialization) |
| `company.environment_releases` | table | screen slice (M0.7, §11 D-M0-1) |
| `company.agent_command_receipts` | table | M0.2a [EXISTS] |
| `/api/v1/missions/*` routes | API | M0.2a–d, screen, cycle |
| MCP tools §5 | MCP | M0.2a–d (+ cycle tools, §11) |
| `assert_task_completion_allowed`, `assert_task_baseline_current`, `build_mission_dispatch_context` | core functions | M0.6a, M0.6b, M0.2c |

---

## 2. M0.0 — minimal model and migration [PROPOSED]

One Alembic revision `m0_0_mission_base` (name indicative), schema `company`, UUID PKs with Python
default, `TimestampMixin`, string FKs (`ForeignKey("company.<table>.id")`), statuses as `String` +
`CheckConstraint` — the conventions in `CLAUDE.md`.

### 2.1 `projects` CHECK

`PROJECT_TYPES = ("creation", "maintenance", "mission")`; drop and recreate
`ck_projects_project_type`. No data change. Downgrade refuses (raises) if any row has
`project_type='mission'` — the operator must decide what to do with them; a downgrade never rewrites
a mission into a common project silently.

### 2.2 `project_missions` (1:1 extension of a mission Project — the single state machine, 04 §Modelo)

| Column | Type | Constraint / note |
|---|---|---|
| project_id | UUID PK, FK `company.projects.id` ON DELETE RESTRICT | a mission project cannot be deleted while the extension exists (`DELETE /projects/{id}` [backend/app/api/routes/project.py:208] gains a 409 for missions) |
| state | String(30) | CHECK in `MISSION_STATES` (§3) |
| paused_from_state | String(30) null | set only while `state='paused'` (CHECK) |
| priority | Integer, default 100 | lower = more urgent; 1–1000 CHECK (cycle spec §6) |
| orchestrator_agent_id | UUID FK `company.agents.id` | exactly one orchestrator (04 Papéis); must also be an active `coordinator` membership (route rule) |
| autonomy_level | String(2), default `N0` | CHECK in (`N0`,`N1`,`N2`,`N3`); **routes refuse anything but `N0` in Onda 1** (08 "Onda 1 opera em N0") |
| brief_artifact_id | UUID FK `company.artifacts.id` null | the `BRIEF.md` artifact |
| current_baseline_id | UUID FK `company.plan_baselines.id` null | the baseline in force |
| deadline_at | timestamptz null | required to leave `draft` |
| budget_limit | Numeric(14,2) null | required to leave `draft` |
| paused_seconds | Integer default 0 | paused time does not count against the deadline (04 §6) |
| state_changed_at | timestamptz | |
| state_reason | Text null | required for pause/cancel/reopen |
| acceptance_request_id | UUID FK `company.approval_requests.id` null | §8 |
| row_version | Integer default 1 | optimistic lock; every transition sends `expected_row_version` |

### 2.3 `mission_project_links` (coordinator ↔ executor projects, D-3)

`id`, `mission_project_id` FK projects (CASCADE), `executor_project_id` FK projects (RESTRICT),
`linked_by` String(150), `UNIQUE(mission_project_id, executor_project_id)`, CHECK
`mission_project_id <> executor_project_id`. Route rule: `mission_project_id` must be a mission;
`executor_project_id` must **not** be a mission (no nested missions in M0). An executor project can
be linked to several missions (04).

### 2.4 Acceptance criteria (needed by the minimal acceptance, §8)

`mission_acceptance_criteria`: `id`, `mission_project_id` FK, `code` String(20) (e.g. `AC-1`),
`statement` Text, `verification_method` Text (how it is proven), `verifier_agent_id` FK agents null,
`verifier_is_marcelo` Boolean, CHECK exactly one verifier, `status` String(20) CHECK in
(`open`,`proven`,`failed`), `evidence_ref` String(500) null, `decided_by` String(150) null,
`decided_at` null, `UNIQUE(mission_project_id, code)`.
`mission_criterion_tasks`: `criterion_id` FK (CASCADE), `task_id` FK `company.project_tasks.id`
(RESTRICT), `UNIQUE(criterion_id, task_id)`; route rule: the task belongs to the mission project or a
linked executor project (04 §Modelo).

`ScopeItemAcceptanceCriterion` [EXISTS backend/app/db/models/system_scope.py:297] was considered and
**not** reused: it hangs off `project_scope_items` (a software-delivery scope element), has no
verifier, status or evidence, and a mission has no `ProjectScope`.

### 2.5 What M0.0 must preserve

- `creation`/`maintenance` projects: no row in `project_missions`, no mission guard, identical API
  responses (test §9.1).
- `ProjectAgentMembership` [backend/app/db/models/orchestration.py:117], `TaskExecutionReview` [:216],
  `ProjectLoopPolicy` [:171] untouched; roles reuse `PROJECT_AGENT_ROLES` [:32] — no new role list.
- Existing criteria, members and reviews keep their ids (no backfill, no rewrite).

### 2.6 Planning records (M0.0b) [PROPOSED, M0.0b, Marcelo 2026-10-29]

M0.0 shipped P1–P8 refusing with `not_recorded` because nothing recorded the data the §3.1 exit
conditions read. M0.0b adds those records; every code of `NOT_RECORDED_CONDITIONS`
(`backend/app/core/mission.py`) is lifted by one of them (table at the end). One Alembic revision on
top of `d3f7a1c9e2b5`. Conventions as §2: schema `company`, UUID PKs with Python default,
`TimestampMixin`, string FKs, enum-like fields as `String` + `CheckConstraint`.

**Who is the planner.** The planner of a plan version is **(a)** the author of that `ProjectPlan`
version, as recorded in `mission_plan_versions`, and **(b)** the mission's orchestrator. (a) wrote the
text being reviewed; (b) conducts the pipeline, disposes of review items and is accountable for the
plan whoever typed it (04 Papéis: the orchestrator owns the plan) — a reviewer who is either of them
reviews their own work. `ProjectPlan` has no author column and `POST /projects/{id}/plans` has no
principal, so the author is recorded on the mission side (below), never inferred.

**Current plan version.** The mission's latest `ProjectPlan` in `draft` (as `_draft_plan` already
reads). Every record below carries the `project_plan_id` it was written against, and **only records of
the current version count** for a stage exit. Registering a new version (i) supersedes the mission's
previous `draft` plans (`status='superseded'`) and (ii) while the mission is `planning`, sets
`planning_stage` back to `draft_plan` — the reviews, dispositions, cross reviews and verification of
the old version stay as history and no longer count. A plan created through the generic
`POST /projects/{id}/plans` becomes the newest draft with no `mission_plan_versions` row, so every exit
refuses `PLAN_VERSION_NOT_REGISTERED` until a version is registered here (fail closed). Exit
conditions from `critical_review` on are **cumulative**: leaving a stage re-checks the record
conditions of every earlier record stage on the current version, so a version swap can never leave a
later stage with nothing to check.

#### 2.6.1 Tables

**`project_tasks` (two new columns) — environment per task (P1 "environment", P2 "environment prerequisites").**

| Column | Type | Constraint / note |
|---|---|---|
| target_environment | String(20) null | CHECK in (`test`,`homolog`,`production`) — the environment the task's work lands in; same vocabulary as the `<environment>` of `task_execution_targets` `publish:<environment>:<target>` (§4.3) plus `homolog`, which the M0.7 `environment_releases` CHECK must add |
| environment_prerequisites | Text[] null | what must exist in that environment before the task runs (e.g. "test database at head"). `NULL` = not recorded; `[]` = recorded as "none". ≤ 20 entries, each 1–500 chars (route) |

Written through the existing `POST /api/v1/tasks` and `PATCH /api/v1/tasks/{id}` (an `agt_` caller
already reaches `PATCH` with `planning.execution.manage`), exactly like `required_skill_ids`: for a
**mission** task only while the mission is `planning` (409 `TASK_ENVIRONMENT_LOCKED`), free for a
common project. A change on a mission task appends `AuditEvent(entity_type="mission",
event_type="mission_task_environment_set")`. Both fields join the §4.2 canonical task content, so a
baselined task whose environment changes is refused by the dispatch guard (`TASK_CONTENT_CHANGED`).

**`mission_plan_versions` — the author of each plan version.**

| Column | Type | Constraint / note |
|---|---|---|
| project_plan_id | UUID PK, FK `project_plans.id` ON DELETE CASCADE | one row per plan version |
| mission_project_id | UUID FK `projects.id` ON DELETE CASCADE | |
| author_type | String(10) | CHECK in (`user`,`agent`) — the authenticated principal, never a body field |
| author_id | UUID | user id or agent id |
| author_name | String(150) | display name at the time |

**`mission_plan_reviews` — per-layer opinions (P3) and cross reviews (P5).**

| Column | Type | Constraint / note |
|---|---|---|
| id | UUID PK | |
| mission_project_id | UUID FK `projects.id` CASCADE | |
| project_plan_id | UUID FK `project_plans.id` CASCADE | the version reviewed; must be current when written |
| kind | String(10) | CHECK in (`layer`,`cross`) |
| layer | String(20) | CHECK in `REVIEW_LAYERS`; for `layer` it must be in the mission's `required_review_layers` (route, 422 `LAYER_NOT_REQUIRED`) |
| reviewer_agent_id | UUID FK `agents.id` | **the authenticated `agt_` agent**; not a body field (the schema forbids extra fields) |
| artifact_version_id | UUID FK `artifact_versions.id` | the review document (artifact + version) |
| summary | Text null | |
| | | `UNIQUE(project_plan_id, kind, layer, reviewer_agent_id)` |

**`mission_review_waivers` — Marcelo's decision that a layer goes without an opinion (P3).**
`id`, `mission_project_id` FK CASCADE, `project_plan_id` FK CASCADE, `layer` (CHECK `REVIEW_LAYERS`),
`reason` Text (CHECK non-blank), `decided_by` String(150), `decided_by_user_id` FK `users.id`,
`UNIQUE(project_plan_id, layer)`.

**`mission_review_items` — what a review raised (P4) and Marcelo's decisions on it (P6).**

| Column | Type | Constraint / note |
|---|---|---|
| id | UUID PK | |
| review_id | UUID FK `mission_plan_reviews.id` CASCADE | the opinion it came from (gives plan version and mission) |
| text | Text | CHECK non-blank |
| disposition | String(10) null | CHECK in (`accept`,`adjust`,`reject`) |
| disposition_reason | Text null | CHECK `(disposition IS NULL) = (disposition_reason IS NULL)` and non-blank when set |
| disposed_by | String(150) null; disposed_at timestamptz null | |
| needs_marcelo_decision | Boolean default false | set by the reviewer on creation or by the disposer; **never cleared** once true (409 `FLAG_CANNOT_BE_CLEARED`) |
| marcelo_decision | String(10) null | CHECK in (`accept`,`adjust`,`reject`); CHECK `marcelo_decision IS NULL OR needs_marcelo_decision` |
| marcelo_reason | Text null; marcelo_decided_by String(150) null; marcelo_user_id FK `users.id` null; marcelo_decided_at null | CHECK all four null together with `marcelo_decision` |

The **effective disposition** of an item is `marcelo_decision` when set, else `disposition`.

**`mission_plan_verifications` — sampled verification of the applied corrections (P7).**
`id`, `mission_project_id` FK CASCADE, `project_plan_id` FK CASCADE, `verifier_agent_id` FK `agents.id`
(the authenticated agent), `sampled_item_ids` UUID[] (review items), `result` String(20) CHECK in
(`confirmed`,`discrepancies`), `notes` Text null.

**`mission_dossiers` — the dossier version for `verifying → awaiting_acceptance` (§8 item 1).**
`id`, `mission_project_id` FK CASCADE, `artifact_version_id` FK `artifact_versions.id`, `file_sha256`
String(64) CHECK `~ '^[0-9a-f]{64}$'`, `registered_by_type` String(10) CHECK (`user`,`agent`),
`registered_by_id` UUID, `registered_by` String(150). The hash is the one declared by the registrant
(the backend container cannot read the repository files — the same limit as M0.6a evidence); when the
artifact version has a `checksum` (`<hex>` or `sha256:<hex>`) they must match (409
`DOSSIER_HASH_MISMATCH`). Re-hashing the file bytes is the acceptance decision's job (§8 item 3, out of
M0.0b).

#### 2.6.2 Routes (all under `/api/v1/missions/{project_id}`, already on the `agt_` admission list)

| Route | Writes | Who | Mission state / stage | Notable refusals |
|---|---|---|---|---|
| `POST /plans` `{name, scope_summary?, estimated_start_date?, estimated_end_date?, estimated_cost?}` | `ProjectPlan(status='draft')` + `mission_plan_versions` (author = caller); supersedes older drafts; stage → `draft_plan` | admin; orchestrator with `mission.orchestrate`; active member with `mission.plan.submit` | `draft` or `planning` | 409 `MISSION_NOT_PLANNING` |
| `POST /plan-reviews` `{project_plan_id, kind, layer, artifact_version_id, summary?}` | `mission_plan_reviews` | **agent only** (`agt_`): active `can_review` member of the mission with `mission.plan.review` | `planning`; `layer` in `critical_review`, `cross` in `cross_review` | 403 `REVIEW_REQUIRES_AGENT`; 409 `REVIEWER_IS_PLANNER`, `PLAN_VERSION_NOT_CURRENT`, `PLAN_VERSION_NOT_REGISTERED`, `PLANNING_STAGE_MISMATCH`, `REVIEW_ALREADY_RECORDED`; 422 `LAYER_NOT_REQUIRED`, `ARTIFACT_VERSION_NOT_FOUND` |
| `POST /plan-reviews/{review_id}/items` `{text, needs_marcelo_decision?}` | `mission_review_items` | the review's own reviewer (same checks as above) | stage of the review's kind | 403 `NOT_REVIEW_AUTHOR` |
| `POST /review-items/{item_id}:dispose` `{disposition, reason, needs_marcelo_decision?}` | disposition, reason, flag | admin; orchestrator with `mission.orchestrate` | `consolidation`, `cross_review`, `decisions` | 409 `ITEM_ALREADY_DECIDED` (after Marcelo's decision), `FLAG_CANNOT_BE_CLEARED`; 422 reason blank |
| `POST /review-items/{item_id}:decide` `{decision, reason}` | Marcelo's decision | **admin user (JWT) only** | `consolidation`, `cross_review`, `decisions` | 403 `MARCELO_DECISION_REQUIRES_ADMIN` (agent token or non-admin); 409 `ITEM_NOT_FLAGGED`, `ITEM_ALREADY_DECIDED` |
| `POST /review-waivers` `{project_plan_id, layer, reason}` | `mission_review_waivers` | **admin user (JWT) only** | `critical_review` | 403 `MARCELO_DECISION_REQUIRES_ADMIN`; 409 `WAIVER_ALREADY_RECORDED` |
| `POST /plan-verifications` `{project_plan_id, sampled_item_ids, result, notes?}` | `mission_plan_verifications` | agent only, same eligibility as a reviewer (not a planner) | `application` | 409 `SAMPLE_ITEM_INVALID` (not an accept/adjust item of this version); 422 `SAMPLE_TOO_SMALL` (fewer than `min(3, n)` of the `n` accepted/adjusted items) |
| `POST /dossier` `{artifact_version_id, file_sha256}` | `mission_dossiers` | admin; orchestrator with `mission.orchestrate`; active member with `mission.dossier.register` | `verifying` | 409 `MISSION_NOT_VERIFYING`, `DOSSIER_HASH_MISMATCH`; 422 `ARTIFACT_VERSION_NOT_FOUND` |
| `GET /planning-records` | — (reads the current version's records) | any authenticated caller (as `GET /missions/{id}`) | any | |

New delegation action keys (project-scoped, §0.2): `mission.plan.review`, `mission.dossier.register`
(`mission.plan.submit` and `mission.orchestrate` already listed). Errors use the §0.3 object form.
Every write appends `AuditEvent(entity_type="mission", entity_id=<mission project id>)` with the §0.5
payload: `mission_plan_version_registered`, `mission_plan_review_recorded`,
`mission_review_item_recorded`, `mission_review_item_disposed`, `mission_review_item_decided`,
`mission_review_waived`, `mission_plan_verification_recorded`, `mission_dossier_registered`,
`mission_task_environment_set`.

#### 2.6.3 Exit conditions read from the records (§3.1)

| Leaving | Record condition (on the current plan version) | Unmet code | Lifts |
|---|---|---|---|
| draft_plan | the newest draft has a `mission_plan_versions` row; every mission task has `target_environment` | `PLAN_VERSION_NOT_REGISTERED`, `TASK_ENVIRONMENT_MISSING` | `ENVIRONMENT_NOT_RECORDED` |
| auto_check (and the P7 re-run) | every mission task has `environment_prerequisites` recorded (`[]` allowed); every `publish:<env>:…` target of a task names that task's `target_environment` | `TASK_ENVIRONMENT_PREREQUISITES_MISSING`, `PUBLISH_TARGET_ENVIRONMENT_MISMATCH` | `ENVIRONMENT_PREREQUISITES_NOT_RECORDED` |
| critical_review | per required layer: a `layer` review by a non-planner, or Marcelo's waiver | `LAYER_REVIEW_MISSING` | `REVIEW_ARTIFACTS_NOT_RECORDED` |
| consolidation | + every item of the version's reviews has a disposition with a non-blank reason | `ITEM_WITHOUT_DISPOSITION`, `ITEM_WITHOUT_REASON` | `REVIEW_DISPOSITIONS_NOT_RECORDED` |
| cross_review | + two `cross` reviews by different non-planner reviewers on different layers | `CROSS_REVIEWS_INSUFFICIENT` | `CROSS_REVIEWS_NOT_RECORDED` |
| decisions | + (cross condition unless `risk_level='low'`) + every flagged item has Marcelo's decision | `FLAGGED_ITEM_UNDECIDED` | `FLAGGED_ITEMS_NOT_RECORDED` |
| application | + validator again + the latest verification of the version, by a non-planner, is `confirmed` with a valid sample | `APPLICATION_VERIFICATION_MISSING`, `APPLICATION_VERIFICATION_DISCREPANCIES` | `APPLICATION_VERIFICATION_NOT_RECORDED` |
| verifying → awaiting_acceptance | a `mission_dossiers` row registered during the current `verifying` stay (`created_at ≥ state_changed_at`) | `DOSSIER_MISSING` | `DOSSIER_NOT_RECORDED` |

"Non-planner" is re-checked at exit, not only at write time. After M0.0b `NOT_RECORDED_CONDITIONS` is
empty: no exit passes for lack of data. Still **not evaluated** (reported, never passed): runtime
installation of skills (§6.1). Out of M0.0b: MCP tools (M0.2a–d), `submit_project_plan` and the
governed baseline approval (M0.2b), `acceptance:request`/`:decide` (§8 items 2–5), the screen,
the cycle (M0.8), `environment_releases` (M0.7). Change-request re-entry into the pipeline (§3.1)
still has no `planning_stage` on the CR row: M0.2b.

**Rollback.** The downgrade drops the six tables and the two `project_tasks` columns; it does not
touch missions, plans or baselines. Records already written are lost on downgrade (they are the
pipeline's evidence: dump them first if a mission is mid-planning).

---

## 3. State machine and `Project.status` projection [PROPOSED, M0.0]

`MISSION_STATES = ("draft","planning","ready","active","verifying","awaiting_acceptance","paused","completed","cancelled")`
(pt-BR labels: rascunho, em planejamento, pronta, ativa, em verificação, aguardando aceite, pausada, concluída, cancelada).

| Mission state | `Project.status` written in the **same transaction** |
|---|---|
| draft, planning, ready | planned |
| active, verifying, awaiting_acceptance | active |
| paused | on_hold |
| completed | completed |
| cancelled | cancelled |

Rules:

1. Only `POST /api/v1/missions/{project_id}:transition` [PROPOSED, M0.0] changes `state`; it writes
   the projection and an `AuditEvent(entity_type="mission", event_type="mission_<from>_to_<to>")`.
2. `PATCH /api/v1/projects/{id}` [EXTEND backend/app/api/routes/project.py:172] refuses `status` **and** `project_type` for a
   mission (409 `MISSION_STATUS_IS_PROJECTED`); other fields stay editable (subject to the brief/baseline
   rules). For a common project `project_type` stays non-patchable as today (`ProjectUpdate` has no such field).
3. Mission completion is never inferred from `Project.status='completed'` (04).

### 3.1 Planning pipeline inside `planning` [PROPOSED, M0.0, Marcelo 2026-10-29]

04 "Validação do plano" (P1–P8). Column `project_missions.planning_stage String(20)` with CHECK in
(`draft_plan`,`auto_check`,`critical_review`,`consolidation`,`cross_review`,`decisions`,`application`,`baseline`),
only meaningful while `state='planning'`. Two more columns are fixed in P1 and locked afterwards (change
request to alter): `risk_level String(10)` CHECK in (`low`,`medium`,`high`) and
`required_review_layers String[]` (subset of `architecture`,`backend`,`frontend`,`security`,`lgpd`,
`infrastructure`,`documentation`,`business`), both required to leave `draft_plan`.
Stage changes go through `POST /api/v1/missions/{project_id}/planning:advance`
`{to, reason, idempotency_key}` [PROPOSED] and are recorded in `mission_decisions` (cycle spec §4).
**`to` must be the next stage in order** (`draft_plan → auto_check → critical_review → consolidation →
cross_review → decisions → application → baseline`); the only exception is `consolidation → decisions`
when `risk_level='low'` (cross review skipped, recorded). Anything else → 409
`PLANNING_STAGE_OUT_OF_ORDER`. The backend checks each exit condition:

| Leaving | Requires |
|---|---|
| draft_plan | a `ProjectPlan` version in `draft` with every task, dependency, role, criterion link, environment, deadline and budget field filled; `risk_level` and `required_review_layers` set |
| auto_check | the plan validator passes on the current `ProjectPlan` version (graph acyclic, author ≠ reviewer including release nodes, environment prerequisites) |
| critical_review | one review artifact per layer in `required_review_layers`, from a reviewer independent of the planner; a missing one only with Marcelo's recorded decision |
| consolidation | every review item has a disposition (accept/adjust/reject) and a reason; items needing a decision flagged |
| cross_review | two cross reviews from reviewers of different layers (stage skipped only when `risk_level='low'`) |
| decisions | no flagged item without Marcelo's decision (`human_only`) |
| application | validator passes again; an independent verifier records that sampled corrections are in the text |

`baseline` ends in the existing baseline approval (§7), which performs `planning → ready`.

**Change request after the baseline (no mission state change).** The mission keeps its state
(`ready`/`active`/`verifying`); the change request carries its own `planning_stage` (same column on the
CR row [PROPOSED]) and runs `auto_check → consolidation → decisions → application → baseline`, adding
`critical_review` (and `cross_review` unless `risk_level='low'`) when it changes scope, criteria or
risk. Only the tasks the CR touches are blocked by the M0.6b guard until the new baseline; the others
keep running. A CR that changes the objective of the mission is refused (409 `CR_CHANGES_OBJECTIVE`):
that is a new mission.
Tests: `test_planning_stage_exit_conditions`, `test_planning_cannot_skip_decisions`,
`test_change_request_reenters_planning`.

Allowed transitions in M0 (anything else → 409 `MISSION_TRANSITION_NOT_ALLOWED`):

| From → To | Who | Preconditions checked by the backend |
|---|---|---|
| draft → planning | Marcelo | brief artifact version `approved` by Marcelo; orchestrator membership active |
| planning → ready | Marcelo | planning pipeline finished (§3.1); ≥1 criterion, each with method + verifier; `deadline_at`, `budget_limit` set; a baseline exists (§7) |
| ready → active | Marcelo, or orchestrator with `mission.orchestrate` | `current_baseline_id` not superseded; dependency missions completed (cycle spec §6.3); orchestrator under its active-mission limit |
| active → verifying | orchestrator or Marcelo | all criteria `proven` |
| verifying → active | anyone who can mark a criterion `failed` | a criterion went `failed` or a task reopened |
| verifying → awaiting_acceptance | orchestrator or Marcelo | dossier artifact version registered during the current `verifying` stay (§2.6, §8) |
| awaiting_acceptance → completed | **only** via the acceptance decision (§8) | all §8 conditions |
| awaiting_acceptance → active | Marcelo (rejecting the dossier) | reason |
| planning/ready/active/verifying → paused | Marcelo; orchestrator only when blocked (reason `blocked:*`) | reason; `paused_from_state` saved |
| paused → paused_from_state | Marcelo | reason |
| any non-terminal → cancelled | Marcelo | reason; queued mission demands archived through `decide_demand(action="archive")`; in-flight runs are **not** killed — they follow the existing uncertain/`confirm_inactive` path [backend/app/core/demand_workflow.py:114-129] |
| completed → active (reopen) | Marcelo | reason (M0 implements; M.1 adds delegation) |

Pause effects (04 §6): `reserve_dispatch` refuses mission tasks while `paused` (keeps them queued,
`WorkflowBlocked`); deadline clock stops (`paused_seconds`); cycle stops nagging. "Pause now" (cancel
running) is **deferred to M.1**; in M0 running work finishes normally.

---

## 4. Guards

### 4.1 M0.6a — global, prospective completion guard [PROPOSED]

`async def assert_task_completion_allowed(db, task, target_status, principal) -> CompletionProof`
in `backend/app/core/task_completion_guard.py` (new). Called for **every new transition** of any
`ProjectTask` (all projects, not just missions) to `done` or `deployed`. It requires:

1. Latest `TaskExecution` (highest `attempt_number`) exists and has `status='verified'`. `completed`
   alone no longer suffices for new transitions, and "no executions at all" no longer passes
   (today's `_ensure_evidence_verified` lets both through [backend/app/api/routes/task.py:488-507]).
2. Its `evidence_ref` passed `verify_evidence` [backend/app/core/task_evidence.py:140] with a typed prefix
   `git:`, `file:` or `db:` (04 §2 "Na Onda 1"); `file:` resolved inside the task's project
   `working_directory_path`; `db:` only for the allowlisted entity types already in
   `backend/app/core/task_evidence.py:48-58`; `git:` commit reachable in that project's repository. `host_execution:`
   and browser evidence are refused until I.5/N.3.
3. A `TaskExecutionReview` on that execution with `status='approved'` whose reviewer is independent:
   `reviewer.agent_id` ≠ the executing agent (resolved: `TaskExecution.assignment_id → TaskAssignment.agent_id`,
   else the dispatched `AgentDemand.target_agent_id` via `task_execution_id`), ≠ any co-author recorded
   on the execution, membership `active` **and** `can_review`, same project (or, for a mission task, the
   mission project). Identity is compared by registered agent id; Porthus = Claude Code, Aramis = Codex
   are one identity each (D-1).
4. Dependencies and subtasks done (existing `ensure_task_dependencies_satisfied`
   [backend/app/core/task_dependencies.py:35] and `_ensure_subtasks_completed` [backend/app/api/routes/task.py:467]).
5. `deployed` additionally requires the task to have been `done` first and, for a mission, an
   `environment_releases` row for `production` citing the task (screen spec §5) — today `deployed`
   has **no** evidence check at all [backend/app/api/routes/task.py:421-424].

Call sites — every writer of `done` found in `develop@dcfe941`, all must call the guard:

| Writer | Location | Today |
|---|---|---|
| `PATCH /tasks/{id}` (and MCP `update_task_status`) | [backend/app/api/routes/task.py:388-447] | evidence only if executions exist; `deployed` unchecked |
| Review approved via PATCH | [backend/app/api/routes/orchestration.py:525-531] | sets `done` directly; no dependency/evidence/subtask check |
| Review refresh (auto) | [backend/app/api/routes/orchestration.py:784-789] | same |
| Governed task approval | [backend/app/core/governed_approval.py:379-388] | checks verified evidence and self-approval; no independent-review requirement |

Additional fixes inside M0.6a: `create_execution_review` [backend/app/api/routes/orchestration.py:452] only rejects
"executor reviews own execution" when `execution.assignment_id` is set; Messages dispatches without an
assignment leave it NULL [backend/app/api/routes/task.py:1033], so the check silently passes — the guard resolves the
executor as in (3). A review created directly with `status='approved'` (no feedback) must be refused
(feedback is only enforced on PATCH today [backend/app/api/routes/orchestration.py:508-509]). The reviewer must be the caller:
an `agt_` caller may only create/decide reviews for its own membership; a human admin may record a
review only with `reviewer_membership_id` of an agent plus `recorded_by` audit (manual verification).

**Historical work:** no backfill, no reopening. Tasks already `done` stay `done`; the screen shows them
as "concluída sem prova (histórica)". Importing historical work (0.x) = create a `TaskExecution`
(`reported`) with real `git:`/`file:`/`db:` evidence + independent review, then transition through the
guard. No invented `run_id`, review or approval; without proof it stays `reported`/`blocked` (12 §5).

Errors: 409 with `code` ∈ `COMPLETION_NO_EXECUTION`, `COMPLETION_EXECUTION_NOT_VERIFIED`,
`COMPLETION_EVIDENCE_INVALID`, `COMPLETION_NO_INDEPENDENT_REVIEW`, `COMPLETION_REVIEWER_IS_EXECUTOR`,
`COMPLETION_DEPENDENCIES_OPEN`, `COMPLETION_SUBTASKS_OPEN`, `DEPLOYED_WITHOUT_RELEASE`.
Audit: `task_completed` / `task_deployed` with `actor` = principal and `payload.proof = {execution_id,
evidence_ref, review_id, reviewer_agent_id}`.

### 4.2 M0.6b — immutable baseline and dispatch guard [PROPOSED]

**Model.** `plan_baselines` gains `content_hash` String(64) and `superseded_at` timestamptz null;
new `plan_baseline_items(id, baseline_id FK CASCADE, task_id FK RESTRICT, content_hash String(64),
UNIQUE(baseline_id, task_id))`. A baseline is immutable: no route updates it; superseding sets
`superseded_at` and the new baseline's id on `project_missions.current_baseline_id`.

**Canonical task content** (`canonical_hash` [EXISTS backend/app/core/governed_approval.py:21] over sorted JSON):
`task_id, title, description, plan_brief, task_type, priority, planning_item_id, change_request_id,
parent_task_id, sorted depends_on_task_ids, sorted execution targets (§4.3), linked criterion codes,
target_environment, environment_prerequisites` (the last two since M0.0b, §2.6),
plus mission-level `brief_artifact_version_id` and the criteria `(code, statement, verification_method,
verifier)` set. **Not** in the hash: assignee (reassignment is a cycle action, §11 D-M0-3), status,
dates, costs. `plan_baselines.content_hash` = hash of the sorted item hashes + mission-level part.

**Guard.** `async def assert_task_baseline_current(db, task) -> None` in
`core/task_baseline_guard.py` (new). Applies when the task's project (or the mission it belongs to) has
a baseline **with items** (legacy baselines without items do not trigger, so common projects are not
blocked — 12 "Limites globais"). Refuses with 409 when:

| Code | Condition |
|---|---|
| `BASELINE_SUPERSEDED` | the baseline cited by the mission is superseded |
| `TASK_NOT_IN_BASELINE` | task added after approval without an approved+applied CR that produced a new baseline |
| `TASK_CONTENT_CHANGED` | recomputed hash ≠ item hash (edited after approval) |
| `BASELINE_FOREIGN_PROJECT` | baseline belongs to another project |
| `MISSION_NOT_ACTIVE` | mission state ∉ {active, verifying} (draft/ready/paused/terminal) |
| `CHANGE_REQUEST_PENDING` | a pending CR targets this task (CR invalidates prior authorization) |

**Placement — all dispatch paths.** The authoritative call is inside `reserve_dispatch`
[backend/app/core/demand_dispatch_guard.py:13], for demands with `origin_type='task'` (resolved by `origin_id`),
right after `ensure_workflow_allowed`. Every path reaches it through `_execute_dispatch`
[backend/app/api/routes/demand.py:1462,1497]: manual `POST /demands/{id}/dispatch` [backend/app/api/routes/demand.py:1995], `POST /tasks/{id}/dispatch`
[backend/app/api/routes/task.py:946], the scheduled pass [backend/app/api/routes/demand.py:1854], legacy approval auto-dispatch [backend/app/api/routes/governance.py:180],
reprocess [backend/app/api/routes/demand.py:687]. An early (non-authoritative) call also runs at the top of
`_dispatch_task_by_id` so no `TaskExecution` row is created for a refused dispatch. Inside the
scheduled pass, a `WorkflowBlocked` keeps the item queued (existing behavior [backend/app/api/routes/demand.py:1899-1905]) —
it is not a failure and consumes no attempt.

**Approval/MCP/reconciliation cannot bypass:** approving a legacy `Approval(project_task)` dispatches
through the same path; `reconcile` [backend/app/api/routes/demand.py:1216] and `run_dispatch_completion_pass` only finalize
existing runs and never start one; `authorize_retry` [backend/app/core/demand_workflow.py:130] raises the attempt
budget but the next start still passes `reserve_dispatch`.

**Replay, retry and uncertainty.** Retry of an uncertain outcome never clears `agent_run_id`
(existing: `requires_reconciliation` [backend/app/core/demand_workflow.py:24] blocks; `confirm_inactive` requires the
run id typed back [:120-129]). A replayed `dispatch_task` with the same idempotency key returns the
original receipt; with a new key while a run is active/reserved/uncertain it returns the existing
demand (existing short-circuit at backend/app/api/routes/task.py:997-1019) — never a second run.

**Revoked permission.** `authorize_action` re-reads delegations on every call (`status='active'`,
validity window) [backend/app/core/deps.py:96-102]; a revocation takes effect on the next request. An already-reserved
run is not cancelled by revocation (M0); the screen flags it (`delegation_revoked_during_run`).

**Rollback.** Migration downgrade drops `plan_baseline_items`, `task_execution_targets` and the two
columns; refused if any mission is `active` (would leave dispatch unguarded) — operator pauses first.

### 4.3 Target serialization (needed by the guard and the cycle) [PROPOSED, M0.6b]

`task_execution_targets(id, task_id FK CASCADE, kind String(20) CHECK in ('worktree','branch','publish'),
target_key String(500), UNIQUE(task_id, kind, target_key))`. Keys are normalized: `worktree` = absolute
realpath; `branch` = `<repo-realpath>#<branch>`; `publish` = `<environment>:<deploy-target>` (e.g.
`production:forgehub`). Implicit target: every Messages run already has `working_path`; for **mission**
tasks `reserve_dispatch` treats `worktree:<realpath(working_path)>` as declared even if absent.

Rule in `reserve_dispatch`: refuse (`WorkflowBlocked("TARGET_BUSY: <kind>:<key> held by #<number>")`,
item stays queued) when another demand with `dispatch_status in ('dispatched','running')` or reserved
or uncertain holds an equal target. Applies to tasks of mission projects in M0; extending it to all
Messages work is an open decision (§11 D-M0-2) because it changes global behavior.

---


### Integration before `done` for mission tasks [PROPOSED, M0.6a, review #41645]

For a task of a mission project whose deliverable is code (it declares a `git:` evidence), the
completion guard (`assert_task_completion_allowed`) additionally requires that the evidenced commit is an
ancestor of the mission mainline (`develop` unless the mission sets another), checked through the
host-bridge git ancestry probe (cycle §3.4). This applies to **every** path that can set `done`, in
particular `PATCH /orchestration/reviews/{id}` [EXISTS backend/app/api/routes/orchestration.py:525-531],
which today sets `task.status="done"` directly on approval: under M0.6a, an approved review on a mission
task sets the execution `verified` and leaves the task `in_review` until `integrate` succeeds. Test:
`test_review_approval_does_not_mark_mission_task_done_before_integration`.

## 5. MCP tool contracts (M0.2a–d) [PROPOSED]

All tools live in `backend/app/mcp/factory_server.py`, call the API with the caller's `agt_`
(`_factory_call` [backend/app/mcp/factory_server.py:65]), and follow §0. Common limits: request body ≤ 64 KiB; text
fields bounded as listed; 30 s client timeout; per-agent rate limit 60 writes/min [EXISTS M0.2a server-side, `agent_write_limiter` in backend/app/core/command_receipts.py; simple
in-process counter, 429 `RATE_LIMITED`; the 64 KiB limit is a route dependency (413 `PAYLOAD_TOO_LARGE`) and is also checked by the MCP before sending]. "Rollback" = how an effect is undone without losing history.

### 5.1 `create_internal_project` (M0.2a) [EXISTS]

- **Input:** `product_version_id: uuid`, `name: str(1..255)`, `description: str?`, `project_type: "mission"|"maintenance"|"creation"` (default `mission`), `working_directory_path: str?` (absolute), `executor_project_ids: [uuid]?` (mission only), `idempotency_key`.
- **Output:** `{project_id, project_type, mission_state?: "draft", project_status: "planned", created: bool}`.
- **Actor/scope:** agent with `mission.manage` scoped to the product (`authorize_action(product_id=...)`); admin user.
- **HTTP:** `POST /api/v1/missions` [EXISTS backend/app/api/routes/mission.py `create_mission`] for missions; for creation/maintenance it calls `build_project` (the existing `create_project`'s body without its commit, backend/app/api/routes/project.py) in-process (never an HTTP self-call), adding the `project_type` the public schema does not expose. 201 / 200 replay.
- **Errors:** 404 version not found/invisible; 409 `PROJECT_NAME_EXISTS_IN_VERSION` (natural key `(product_version_id, lower(name))`, checked under advisory lock — returns the existing id in the body so the caller can reuse it, M0.1 idempotent registration); 422 non-absolute path; 403.
- **Idempotency:** receipt (§0.4) + natural key.
- **Audit:** `project_created` (+ `mission_created`), actor = agent.
- **Rollback:** a `draft` mission with no tasks can be cancelled (`:transition → cancelled`); never hard-deleted by tool.
- **As built (M0.2a):** an agent caller is the mission's orchestrator when `orchestrator_agent_id` is omitted, and becomes the active `coordinator` of a creation/maintenance project it registers (so it can staff it with §5.2); mission-only fields on another type → 422 `MISSION_ONLY_FIELDS`; an agent registering a non-mission without a key → 422 `IDEMPOTENCY_KEY_REQUIRED`; the name check trims and ignores case; no unique index was added (the natural key is checked under `pg_advisory_xact_lock`, so a plain `POST /projects` can still create a same-named common project).

### 5.2 `manage_project_members` (M0.2a) [EXISTS]

- **Input:** `project_id`, `operations: [{op: "add"|"update"|"suspend"|"release", agent_id, role ∈ PROJECT_AGENT_ROLES, can_review?: bool, can_approve?: bool, responsibilities?: str(≤2000), valid_to?: date}]` (≤20 ops), `idempotency_key`.
- **Output:** `{memberships: [ProjectAgentMembershipOut], violations: []}`.
- **Actor/scope:** `mission.manage` on that project; admin.
- **HTTP:** `POST /api/v1/missions/{project_id}/members:apply` [EXISTS backend/app/api/routes/mission.py `apply_project_members`] (one transaction) reusing the existing membership functions, extracted without their commit as `add_project_membership`/`apply_membership_update` [backend/app/api/routes/orchestration.py].
- **As built (M0.2a):** the agent caller must also be the project's active `coordinator` (403 `NOT_PROJECT_COORDINATOR`; a missing delegation is 403 `DELEGATION_REQUIRED`); `add` on a suspended/released member reactivates the same row, on an active one is `MEMBER_ALREADY_EXISTS`; the charter check refuses a code role when a `never_does` line forbids editing code, and any role a line names; on a creation/maintenance project the coordinator rule is "at most one"; a completed/cancelled mission → 409 `MISSION_TERMINAL`. Response also lists `applied: [{op, agent_id, membership_id}]` and the whole roster.
- **Validation (04 "Regras checadas ao nomear"):** exactly one active `coordinator` and it equals `orchestrator_agent_id`; code roles (`developer`, `architect`, `data_engineer`) only for external-runtime agents (`runtime_type ∈ claude|codex|agy`, "coding only by external agents"); agent active; `can_approve` refused for agents in M0 (approval is Marcelo's); charter `never_does` respected (`AgentCharter.never_does` [backend/app/db/models/operations.py:67]) — violations returned as 422 `MEMBER_RULE_VIOLATION` with the list.
- **Errors:** 404, 403, 409 `LAST_COORDINATOR` (cannot remove the only coordinator of a non-terminal mission), 422.
- **Idempotency:** receipt + natural `UNIQUE(project_id, agent_id)`.
- **Audit:** one `membership_<op>` per op.
- **Rollback:** `release` (status `released`), never delete — reviews RESTRICT memberships [backend/app/db/models/orchestration.py:225-229].

### 5.3 `submit_project_plan` (M0.2b) — submits only

See §7. **Input:** `project_id`, `plan: {name, scope_summary, estimated_start_date?, estimated_end_date?, estimated_cost?}`, `task_ids: [uuid]` (the tasks the baseline will authorize), `idempotency_key`. **Output:** `{plan_id, approval_request_id, plan_hash, checks: [{key, passed, detail}], status: "pending_approval"}`. **Actor:** `mission.plan.submit`. **HTTP:** `POST /api/v1/missions/{project_id}/plans:submit` [PROPOSED]; 201 / 200 replay; 409 `PLAN_CHECKS_FAILED` (with the failing checks) / `PLAN_ALREADY_PENDING` (returns its id) / `MISSION_NOT_DRAFT_OR_CR`; 422. **Audit:** `plan_submitted`. **Rollback:** `POST /api/v1/missions/{id}/plans/{plan_id}:withdraw` [PROPOSED] marks the request `withdrawn` (new value in the governed request status vocabulary, §11 D-M0-4); the plan stays `draft`. **Never** accepts an approver token, approver name or `approved` flag; any such field is a 422.

### 5.4 `add_task_dependency` (M0.2b)

- **Input:** `task_id`, `depends_on_task_id`, `dependency_type` (default `finish_to_start`; M0 accepts only it — the gate only understands finish-to-start), `idempotency_key`.
- **Output:** `TaskDependencyOut` + `baseline_impact: "none"|"requires_change_request"`.
- **Actor/scope:** `planning.execution.manage` on the task's project; both tasks in the same mission scope (mission project or linked executor projects), else 404.
- **HTTP:** `POST /api/v1/tasks/{task_id}/dependencies` [EXISTS backend/app/api/routes/task.py:708] admitted for `agt_` [EXTEND main.py] plus `authorize_action` [EXTEND backend/app/api/routes/task.py:713].
- **Errors:** 409 cycle (existing [backend/app/api/routes/task.py:723-736]); 409 `TASK_IN_BASELINE` when the dependent task is in a current baseline (adding a dependency changes its hash → CR required); 400 self-dependency.
- **Idempotency:** receipt + natural `(task_id, depends_on_task_id)` [PROPOSED unique index; today duplicates are allowed].
- **Audit:** `task_dependency_added`. **Rollback:** existing `DELETE` [backend/app/api/routes/task.py:756] (same baseline rule).

### 5.5 `assign_task` (M0.2c)

- **Input:** `task_id`, `agent_id`, `reason: str(1..2000)`, `idempotency_key`.
- **Output:** `{assignment_id, membership_id, previous_assignment_id?, task_status}`.
- **Actor/scope:** `planning.execution.manage` (and `mission.orchestrate` when it replaces an active assignment).
- **HTTP:** `POST /api/v1/missions/{project_id}/tasks/{task_id}:assign` [PROPOSED] which releases the previous active assignment (`status='released'`, `unassigned_at`) and calls the existing creation logic [backend/app/api/routes/task.py:807] with `membership_id` set (automated dispatch requires it, [backend/app/db/models/task.py:244-251]).
- **Rules:** target has an `active` membership with an executor role; agent ≠ the task's designated reviewer (§5.11) and ≠ reviewer of any open review of the task; refuse while a run is active/reserved/uncertain (409 `TASK_RUN_IN_FLIGHT`).
- **Audit:** `task_assigned` / `task_reassigned` with reason. **Rollback:** reassign again (history kept).

### 5.6 `dispatch_task` (M0.2c)

- **Input:** `task_id`, `command_text?: str(≤4000)` (extra instruction; part of the demand content hash), `scheduled_at?: datetime` (future → scheduled, see cycle spec), `idempotency_key`.
- **Output:** `{task_id, demand_id, demand_number, dispatch_status, agent_run_id?, scheduled_at?, task_status}` (shape of `TaskInboxDispatchOut` [backend/app/api/routes/task.py:946] + `scheduled_at`).
- **Actor/scope:** `planning.execution.manage` on the project; human admin via screen.
- **HTTP:** `POST /api/v1/tasks/{task_id}/dispatch` [EXISTS backend/app/api/routes/task.py:946], extended to accept `scheduled_at` and `idempotency_key` and to call `authorize_action` for `agt_` [EXTEND]. With `scheduled_at` in the future it creates the linked demand with `scheduled_at` and does **not** reserve; `run_scheduled_dispatch_pass` starts it when due through `reserve_dispatch`.
- **Guards (in order):** M0.6b baseline (§4.2) → mission state → task not terminal → dependencies [backend/app/api/routes/task.py:1021] → assignment with membership (missions: required, no responsibility-area fallback) → target serialization (§4.3) → capacity/one-per-agent (existing).
- **Errors:** 409 guard codes; 409 `Execution capacity is occupied` stays queued (not an error for scheduled items); 502 `UPSTREAM_UNCERTAIN` (existing [backend/app/api/routes/task.py:1144-1151]).
- **Idempotency:** receipt; plus the no-second-run rule (§0.4).
- **Audit:** `task.dispatched` with actor = principal [EXTEND backend/app/api/routes/task.py:1161-1167], `payload.context_manifest` (§6).
- **Limit:** one in-flight run per task; global cap/one-per-agent unchanged. **Rollback:** a queued/scheduled demand is withdrawn with `decide_demand(action="archive")` [backend/app/core/demand_workflow.py:186]; a started run is never killed by rollback.

### 5.7 `report_task_execution` (M0.2c) — DONE is a report, not acceptance

- **Input:** `task_id`, `execution_id?` (default: the caller's latest open execution of that task), `status: "reported"|"failed"|"blocked"`, `summary: str(1..10000)`, `evidence: [str]` (each `git:<sha>` / `file:<relpath>` / `db:<type>:<uuid>`, 1..20), `idempotency_key`.
- **Output:** `{execution_id, status: "reported"|"failed", verification: "queued"}`.
- **Actor/scope:** `mission.execution.report` **and** the caller is the executor of that execution (assignment agent or demand target). Anyone else → 403.
- **HTTP:** `POST /api/v1/tasks/{task_id}/executions/{execution_id}:report` [PROPOSED] (the generic PATCH [backend/app/api/routes/task.py:632] is not given to agents: it can set `verified`).
- **Rules:** the caller can never set `verified`/`completed`; only `run_evidence_verification_pass` [backend/app/core/task_evidence.py:164] promotes `reported → verified`. Evidence outside the project root or on another project's repo is refused at report time (422 `EVIDENCE_OUT_OF_SCOPE`).
- **Audit:** `execution_reported`. **Rollback:** a new report supersedes (keeps history in audit); the execution row is never deleted.

### 5.8 `attach_project_document` (M0.2d) [EXISTS]

- **Input:** `project_id`, `entity_type ∈ {project, planning_item, project_task, mission_criterion}`, `entity_id`, `doc_path` (relative, under `docs/missions/<slug>/` or the project's `docs/`), `register_artifact: bool`, `artifact_type?`, `idempotency_key`.
- **Output:** `{doc_link_id, artifact_id?, artifact_version_id?, content_hash}`.
- **Actor/scope:** member of the project (any active role); `documentation` role for the mission brief/dossier.
- **HTTP:** existing `POST /api/v1/docs/links` [backend/app/api/routes/docs.py:401] and artifact routes [backend/app/api/routes/artifact.py:110,233] composed by `POST /api/v1/missions/{project_id}/documents` [EXISTS backend/app/api/routes/mission.py `attach_project_document`] (one transaction; in-process through `build_doc_link` [backend/app/api/routes/docs.py] and `build_artifact`/`build_artifact_version` [backend/app/api/routes/artifact.py], the routes' bodies without their commit).
- **Errors:** 422 `DOC_PATH_NOT_ALLOWED` (absolute, `..`, symlink escaping the root after realpath, outside allowed roots), 404 entity outside project.
- **Idempotency:** receipt + natural `(doc_path, entity_type, entity_id)`.
- **Audit:** `document_attached` with hash. **Rollback:** existing `DELETE /docs/links/{id}` [backend/app/api/routes/docs.py:434]; artifact versions are never deleted.
- **As built (M0.2d):** `doc_path` is relative to the Docs tree (`/docs`, the base `DocLink.doc_path` always had), under `missions/<slug>/` (mission) or `projects/<slug>/` (any project), slug = project name lowercased, non-alphanumerics as `-` (the `system_scope.py` convention) — rules in `backend/app/core/mission_documents.py`; the 422 carries `reason` (`absolute`, `parent_reference`, `not_normalized`, `invalid_characters`, `outside_allowed_roots`, `symlink_escape` — a symlinked project folder counts) and `allowed_prefixes`; a missing file is 404 `DOC_FILE_NOT_FOUND`. `content_hash` = sha256 hex of the bytes, also the version's `checksum`. `project_task` is stored as DocLink `task`. **`mission_criterion` is refused (422 `ENTITY_TYPE_NOT_SUPPORTED`)**: `doc_links`' CHECK has no such type and widening it is a migration, deferred to the criteria write route (M0.2). Authority is the active membership (no delegation action); a non-member agent gets 404 `PROJECT_NOT_FOUND`; a person must be admin. The brief/dossier is `BRIEF.md`, `DOSSIE-DE-VALIDACAO.md` or `artifact_type=context_brief` (403 `DOCUMENTATION_ROLE_REQUIRED`). With `register_artifact`, the artifact is the one already linked to that `doc_path` (DocLink `artifact`) or a new one (`reference_doc` by default): a new version only when the hash changed (409 `ARTIFACT_LOCKED`, `ARTIFACT_TYPE_MISMATCH`). 201 when a link or version was created, 200 otherwise; same switch, limits and receipts as M0.2a. Attaching does not set `project_missions.brief_artifact_id`.

### 5.9 `get_my_mission_role` (M0.2d, read) [EXISTS]

- **Input:** `project_id`. **Output:** `{project_id, mission_state, role, can_review, responsibilities, orchestrator, my_tasks: [{task_id, number, title, status, execution_state}], my_reviews: [{execution_id, task_id}]}`.
- **Actor/scope:** the caller only; not a member → 404 (no existence leak). **HTTP:** `GET /api/v1/missions/{project_id}/me` [EXISTS backend/app/api/routes/mission.py `get_my_mission_role`]. Read-only, no audit, no idempotency.
- **As built (M0.2d):** member = active `ProjectAgentMembership`; also answers for a creation/maintenance project (`mission_state` null). Executor = an active `TaskAssignment`; reviewer = a `TaskExecutionReview` held by the caller's membership; each task carries `relations` and `execution_state` (latest `TaskExecution.status`). A person gets 403 `AGENT_ONLY`. Behind `MISSION_TOOLS_ENABLED` (503 off).
- **`GET /api/v1/missions/{id}` restricted (M0.2d, 09 "lacunas")**: admins and active members only; anyone else gets the same 404 `MISSION_NOT_FOUND` as a missing mission. Not switchable.

### 5.10 `list_my_tasks` (M0.2d, read) [EXISTS]

`GET /api/v1/missions/me/tasks?state=` [EXISTS backend/app/api/routes/mission.py `list_my_tasks`] — tasks where the caller is executor or reviewer across missions it belongs to; same item shape as 5.9 (plus `project_id`). As built: `state` = `open` (default: not `done`/`deployed`/`cancelled`), `all` or one task status (422 `INVALID_STATE_FILTER` otherwise); missions only; output `{state, tasks}`.

### 5.11 `request_task_review` (needed by the screen and cycle; proposed as part of M0.2c — §11 D-M0-5)

- **Input:** `task_id`, `execution_id`, `reviewer_agent_id`, `idempotency_key`.
- **Effect:** creates `TaskExecutionReview(status='pending')` via the existing route logic [backend/app/api/routes/orchestration.py:452] **and** a Messages Task to the reviewer (`origin_type='task'`, `origin_id=task_id`, body: execution summary + evidence list + review instructions; `requires_response=false`), dispatched through the normal queue. The reviewer decides with `PATCH /orchestration/reviews/{id}` [backend/app/api/routes/orchestration.py:496] using its own `agt_` (admitted for that path [EXTEND main.py]); approval then lets the completion guard pass.
- **Rules:** reviewer ≠ executor/co-author (§4.1.3); `can_review`; execution `verified`.
- **HTTP:** `POST /api/v1/missions/{project_id}/tasks/{task_id}:request-review` [PROPOSED]. **Audit:** `review_requested`.

### 5.12 `return_task_for_correction` (proposed with 5.11)

`POST /api/v1/missions/{project_id}/tasks/{task_id}:return` [PROPOSED]; input `reason` (required),
`execution_id`. If an open review exists it becomes `changes_requested` with the reason as feedback;
otherwise an `AuditEvent(mission_task_returned)`; task `→ in_progress`; no automatic redispatch
(orchestrator dispatches explicitly, 04 §1). Allowed to Marcelo and to an agent with
`mission.orchestrate` that is **not** the executor.

---

## 6. Minimal dispatch context by allowlist [PROPOSED, M0.2c]

`build_mission_dispatch_context(db, task) -> MissionDispatchContext` replaces the free composition in
`_dispatch_task_by_id` [backend/app/api/routes/task.py:1066-1085] **for mission tasks only** (common tasks unchanged). The
body is built only from these fields, each with source id + content hash recorded in
`context_manifest`:

| Allowed | Source |
|---|---|
| task number, title, description, plan_brief, type, priority | `project_tasks` |
| baseline id and task content hash | `plan_baseline_items` |
| mission name, objective section of the **approved** brief version | artifact version (approved) |
| linked criteria `code + statement + verification_method` | `mission_acceptance_criteria` |
| predecessor tasks `number + title + status` (no results) | `task_dependencies` |
| executor role, reviewer name, working_path, declared targets | membership, `task_execution_targets` |
| open critique/return reason for this task (correction tasks) | review feedback / audit |
| evidence-format instruction and completion-report contract | constants already in use [backend/app/api/routes/task.py:1077-1085], `core/completion_report.py` |

Never included: other tasks' results or messages, Knowledge Base search results, Hindsight recall,
memory files, personal data (Maia) or client data (Lara), secrets, URLs with tokens, other missions.
The allowlist covers only the **dispatch body**; the runtime's own hook (`knowledge_cycle.py`) is
contained separately by C.2a/C.2.R (12 §8) and is not part of this contract.

`context_manifest = [{source, id, hash}]` is stored in the `task.dispatched` audit payload (no new
column). Size cap 32 KiB; over the cap → 422 `CONTEXT_TOO_LARGE` (the orchestrator splits the task;
the builder never truncates silently).

Rehearsal (M0.4) runs this builder against the **test** database with fixture canaries
(`CANARY-MAIA-<uuid>` in a fictitious personal note, `CANARY-LARA-<uuid>` in a fictitious client
record, `CANARY-KB-<uuid>` in a fixture KB file) and asserts none appears in the body (§9.6). It uses
the simulated runner and test `agt_` credentials, never production profiles, bridge or credentials.

---


### 6.1 Mission context pack and executor skills [PROPOSED, Marcelo 2026-10-29]

04 §8. Two additions on top of the allowlist above:

**Context pack.** Table `mission_context_versions(id uuid PK, project_id FK projects, version int,
content_hash String(64), sources JSONB, created_by_type/created_by_id, reason Text not null, created_at)`
with `UNIQUE(project_id, version)`. `sources` lists the canonical items the version is built from (brief
artifact version, baseline id, decision row ids, integrated commits, annotations, lessons), never their
copied text when the item already lives elsewhere. A new version is written by the cycle after any
decision, integration or annotation (cycle spec §3.6). Every mission dispatch stores
`context_version_id` and the hash of the allowlisted slice it carried; the completion report gains an
optional `CONTEXT_MISSING:` line, recorded as a pack item. A delivery made on a superseded version that
the newer one changes materially is `return`ed (cycle §3.4), not reviewed.

**Skills.** Column `project_tasks.required_skill_ids UUID[] not null default '{}'` [PROPOSED, M0.0],
editable only while the mission is `planning` (afterwards by change request). The P2 auto check
(§3.1) adds, per task: each required skill exists and is `active`; the assigned executor **and** reviewer
hold it in `agent_skills`; and, when the skill has a runtime file, it is present in that agent's runtime
(through the existing profile/skills readers, read-only). A gap is a consolidation item, never a silent
pass. `propose_skill_change(task_id, kind in (assign_other_agent, grant_to_agent, create_skill),
skill_id?, agent_id?, reason, idempotency_key)` [PROPOSED tool] only records a proposal routed to the
skill's canonical owner (Athos for shared/Foundation skills); granting or creating a skill stays with that
owner and its approval. Tests: `test_auto_check_flags_missing_skill_for_executor_and_reviewer`,
`test_required_skills_locked_after_baseline`, `test_propose_skill_never_grants`,
`test_dispatch_records_context_version`, `test_stale_context_delivery_returned`.

## 7. Plan submission and baseline approval [PROPOSED, M0.2b + M0.6b]

1. `submit_project_plan` creates/updates a `ProjectPlan` in `draft` [backend/app/db/models/project.py:188] and runs
   the automatic checks of 04 "Validação do plano" that M0 can compute: every criterion has ≥1 task;
   every listed task has an active assignment with an executor role and a designated reviewer distinct
   from the executor; dependencies acyclic (re-checked); every task in the mission scope; deadline and
   budget set; brief approved. Checks that need M.1 (critical path vs deadline, document owners,
   risks list, budget sum) are reported as `not_evaluated`, never as passed.
2. It opens an `ApprovalRequest(target_type='project_plan', target_id=plan_id,
   target_hash=<plan_hash>, approval_type='mission_plan_baseline', requested_by_type='agent')`
   [model EXISTS backend/app/db/models/governance.py:187]. `policy_evaluation_id` is NOT NULL [backend/app/db/models/governance.py:206], so M0.6b
   seeds a `Policy`/`PolicyVersion`/`PolicyBinding` `mission_plan_approval` with
   `rules_snapshot = {deny_self_approval: true, human_only: true, expires_hours: 168}` (data migration).
3. Marcelo approves on the screen through `POST /governed/approval-requests/{id}:decide`
   [EXISTS backend/app/api/routes/governed_approval.py:64], extended [EXTEND :72-80] with a `project_plan` branch that:
   requires `principal_type='user'` and `is_admin` (`human_only`), recomputes the plan hash and refuses
   on mismatch (409 `PLAN_CHANGED_SINCE_SUBMISSION`), then in one transaction sets the plan `approved`,
   creates the `PlanBaseline` + `plan_baseline_items`, supersedes the previous baseline, sets
   `project_missions.current_baseline_id`, records `ApprovalDecisionRecord` (idempotent by key
   [backend/app/db/models/governance.py:246]).
4. For mission projects the generic shortcuts are refused: `POST /projects/plans/{id}/approve`
   [backend/app/api/routes/project.py:282] and `POST /projects/{id}/baselines` [backend/app/api/routes/project.py:306] return 409
   `USE_GOVERNED_PLAN_APPROVAL`. (For common projects they stay as they are; note they have no
   authorization beyond login today — not changed by M0, listed in §11 D-M0-6.)
5. Approval does **not** dispatch (04 §1 "não despacha automaticamente").
6. After baseline: any change goes through `ChangeRequest` [backend/app/api/routes/project.py:374]; a CR in `approved` is
   applied by submitting a new plan that references it (`plan.change_request_id` — reuse
   `ProjectTask.change_request_id` for new tasks); the new approval creates the next baseline.

---

## 8. Minimal formal acceptance (M0) [PROPOSED]

Per 12 "Aceite mínimo persistido da M0" and 04 "Aceite mínimo M0":

1. Scriba prepares `docs/missions/<slug>/DOSSIE-DE-VALIDACAO.md` manually (template
   `docs/plano-integrado/modelos/DOSSIE-DE-VALIDACAO.md`) and registers it as an Artifact version
   (§5.8). The `awaiting_acceptance` transition requires that version.
2. `POST /api/v1/missions/{project_id}/acceptance:request` [PROPOSED] (orchestrator or Marcelo) opens
   `ApprovalRequest(target_type='mission_dossier', target_id=project_id,
   target_revision_id=<artifact_version_id>, target_hash=sha256(<file bytes>),
   approval_type='mission_acceptance')`, policy `mission_acceptance` (`human_only`, `deny_self_approval`).
3. Marcelo decides through the same `:decide` route with a `mission_dossier` branch [EXTEND
   backend/app/api/routes/governed_approval.py:72-80]. `approved` is accepted only if, re-checked at decision time:
   every criterion `proven` with `evidence_ref`; every task linked to criteria is `done`/`deployed`
   through the guard (or `cancelled` with an approved CR); no open `changes_requested` review; dossier
   file hash unchanged; principal is user + admin. Then, same transaction: mission `completed`,
   projection `completed`, `acceptance_request_id` set, delegations with `project_id` = mission and
   action `mission.orchestrate`/`planning.execution.manage` revoked (04 §3 "autoridade do orquestrador
   revogada"), audit `mission_accepted`.
4. `rejected` (or `changes_requested`) → mission back to `active`, reason stored; critiques are written
   by Marcelo in the dossier (M0) — the critique entity is M.1.
5. Never inferred from `Project.status`, never from a name in Markdown, never from an agent token;
   `mission.accept` delegation is refused in M0 (403 `ACCEPTANCE_RESERVED_TO_MARCELO`).

Criterion decisions: `POST /api/v1/missions/{project_id}/criteria/{id}:decide` [PROPOSED]
`{status: proven|failed, evidence_ref, reason}`; only the criterion's verifier (agent with `agt_`) or
Marcelo; the verifier must not be the executor of any linked task (409 `VERIFIER_IS_EXECUTOR`); all
linked tasks must be done through the guard before `proven`.

---

## 9. Planned tests

Backend tests run only against the isolated test database (`ENVIRONMENT=test`, conftest guard T.1);
pure-logic tests use `--noconftest` under `backend/tests_unit/`. Each test creates and cleans its own
rows (CLAUDE.md test conventions).

### 9.1 M0.0 — `backend/app/tests/test_mission_base.py`

| Test | Proves |
|---|---|
| `test_migration_upgrade_downgrade_roundtrip` | CHECK accepts `mission`; downgrade restores the old CHECK; downgrade refuses while a mission row exists |
| `test_common_projects_unchanged` | create/patch/list of `creation`/`maintenance` projects return identical shapes; no `project_missions` row; no mission guard fires |
| `test_project_create_schema_does_not_accept_mission` | `POST /projects` with `project_type` is ignored/422 — missions only via `/missions` |
| `test_patch_status_refused_for_mission` | `PATCH /projects/{id}` `status`/`project_type` → 409 `MISSION_STATUS_IS_PROJECTED` |
| `test_state_projection_all_transitions` | each allowed transition writes the right `Project.status` in the same transaction; each disallowed pair → 409 |
| `test_transition_preconditions` | draft→ready refused without approved brief / criteria / deadline / budget / baseline |
| `test_autonomy_level_n0_only` | any level ≠ N0 refused in Onda 1 |
| `test_existing_members_reviews_preserved` | memberships/reviews created before migration keep ids and fields |
| `test_mission_delete_refused` | `DELETE /projects/{id}` on a mission → 409 |

### 9.2 M0.6a — `backend/app/tests/test_task_completion_guard.py`

| Test | Proves |
|---|---|
| `test_done_without_execution_refused` | new transition without any execution → 409 (all projects) |
| `test_done_with_reported_not_verified_refused` | `reported`/`completed` but not `verified` → 409 |
| `test_invented_evidence_refused` | `file:` missing / mtime before start / `git:` unknown sha / `db:` absent row → not verified |
| `test_evidence_from_other_project_refused` | path outside project root, repo of another project → refused |
| `test_reviewer_equals_executor_refused` | same agent id (with and without `assignment_id`) → 409 `COMPLETION_REVIEWER_IS_EXECUTOR` |
| `test_reviewer_without_can_review_refused` | membership lacks `can_review` or is suspended |
| `test_all_writers_call_guard` | PATCH `/tasks`, MCP `update_task_status`, PATCH `/orchestration/reviews` approve, review refresh, governed task approval — each refused without proof |
| `test_deployed_requires_done_and_release` | `deployed` refused without prior `done` and a production release row |
| `test_historical_done_untouched` | pre-existing `done` tasks keep status; no backfill |
| `test_historical_import_through_guard` | reported execution + real evidence + independent review → done; without proof stays reported |
| `test_audit_actor_is_principal` | `task_completed` actor equals the authenticated principal, never `system` |
| `test_review_created_approved_without_feedback_refused` | direct approved review without feedback → 422 |

### 9.3 M0.6b — `backend/app/tests/test_task_baseline_guard.py`

| Test | Proves |
|---|---|
| `test_edit_after_approval_blocks_dispatch` | changing title/description/plan_brief/criteria/brief → `TASK_CONTENT_CHANGED` |
| `test_added_task_without_cr_blocked` | `TASK_NOT_IN_BASELINE` |
| `test_baseline_of_other_project_blocked` | `BASELINE_FOREIGN_PROJECT` |
| `test_cr_pending_blocks_and_new_baseline_unblocks` | pending CR blocks; applied CR + new approval unblocks; old authorization not reusable |
| `test_all_dispatch_paths_guarded` | `/tasks/{id}/dispatch`, `/demands/{id}/dispatch`, scheduled pass, legacy Approval auto-dispatch, reprocess — all refused (scheduled stays queued, no attempt consumed) |
| `test_retry_does_not_duplicate_run` | replay same key → same receipt; new key while active/uncertain → existing demand, one `agent_run_id` |
| `test_uncertain_keeps_run_id` | uncertain outcome keeps `agent_run_id`; only `confirm_inactive` with typed id releases |
| `test_revoked_delegation_refused` | revoke then dispatch → 403; reserved run flagged, not killed |
| `test_paused_mission_not_dispatched` | paused → stays queued |
| `test_target_serialization` | two tasks same worktree/branch/publish target → second stays queued with `TARGET_BUSY` |
| `test_common_project_legacy_baseline_not_blocked` | project with an item-less legacy baseline dispatches as before |
| `test_migration_roundtrip_refuses_with_active_mission` | downgrade refused while a mission is active |

### 9.4 M0.2a–d — `backend/app/tests/test_mission_mcp.py` (+ `tests_unit/test_mission_mcp_contract.py`)

| Test | Proves |
|---|---|
| `test_create_internal_project_idempotent` | same key → same project; same name in version → 409 with existing id (M0.1 idempotent registration) |
| `test_members_rules` | non-member, invalid role, two coordinators, code role for Hermes agent, `can_approve` for agent → refused |
| `test_non_member_gets_404_not_403_on_reads` | no existence leak across projects |
| `test_submit_plan_never_approves` | request pending; no baseline; approver fields → 422; agent cannot decide (`human_only`) |
| `test_plan_hash_mismatch_on_decide` | edit after submit → 409 at decision |
| `test_add_dependency_cycle_refused` / `test_dependency_on_baselined_task_requires_cr` | |
| `test_assign_refused_when_reviewer_or_in_flight` | |
| `test_dispatch_guards_order_and_retry` | guard order; retry without duplicate |
| `test_report_cannot_set_verified` | executor reports; `verified` only from the verification pass; non-executor → 403 |
| `test_attach_document_path_rules` | absolute, `..`, symlink escape, other project → refused [EXISTS M0.2d; also `test_attach_document_idempotent_versioned_and_role_gated`, unit `tests_unit/test_mission_documents.py`] |
| `test_my_role_only_own` | agent sees only its own role/tasks [EXISTS M0.2d; also non-member 404 on `GET /missions/{id}`] |
| `test_missing_or_foreign_agt_token` | missing → tool error, no fallback; another agent's token cannot act as the caller |
| `test_tools_disabled_flag` | `MISSION_TOOLS_ENABLED=false` → 503, data untouched |
| `test_error_mapping` (unit) | each HTTP status → MCP message format with `code` |

### 9.5 M0.2 middleware — `backend/tests_unit/test_mission_auth_paths.py`

Proves `agt_` reaches exactly the new mission paths and the listed task sub-paths, and still cannot
reach `POST /projects/plans/{id}/approve`, baselines, `/governed/approval-requests/*:decide` for
`project_plan`/`mission_dossier` decisions (route refuses agents), or any other path.

### 9.6 Context allowlist — `backend/app/tests/test_mission_dispatch_context.py`

`test_canaries_absent` (Maia/Lara/KB canaries never in the body), `test_manifest_lists_every_source`,
`test_context_too_large_refused`, `test_common_task_body_unchanged`.

### 9.7 Screen and cycle tests

Listed in the two companion specs (§9 of each).

---

## 10. Deferred to M.1 (Onda 3) — explicitly out of M0

- Full `/missions` module features beyond the executions screen: brief editor and version workflow,
  critique entity and states (04 §4), automatic dossier generation (M.1n), lessons/metrics to Evolução.
- Per-task named verifier entity and the full naming-rule checker (M.1e); orchestrator authority grant
  and substitute (M.1f: Atlas default, 24 h escalation); mission channel (M.1j).
- Plan validation checks that need data M0 does not have (critical path vs deadline, document owners,
  risk list, budget sum) and plan generation from phases (M.1h).
- Context by recipient (M.2) and broad retrieval (only after C.2b/C.2b.R).
- `mission.accept` delegation; "pause now" cancelling running work; health traffic light with all
  signals of 04 (cost, client, routines); client portal acceptance (E.3).
- Autonomy above N0 (needs G.5/G.6/G.10/G.11b).
- Extending target serialization to all Messages work (§11 D-M0-2) unless Marcelo decides otherwise.

---

## 11. Open decisions for Marcelo

| # | Decision | Recommendation |
|---|---|---|
| D-M0-1 | The executions screen and the decision cycle have no slice id in `onda1-tarefas.json`. Add **M0.7 (screen, Dartan executes UI, Porthus reviews)** and **M0.8 (cycle, Porthus executes, Dartan reviews)**, both after M0.2c/M0.6a/b, before M0.R | Add them; Athos updates the matrix and projections in one change |
| D-M0-2 | Target serialization (same worktree/branch/production) for **all** Messages work, not only mission tasks | Yes for `publish:production:*` globally (the 28/10 incident was outside any mission); mission-only for worktree/branch in M0 |
| D-M0-3 | Reassignment of a baselined task without CR | Allowed (assignee not in hash), recorded with reason, eligibility + reviewer ≠ executor enforced |
| D-M0-4 | Add `withdrawn` to governed approval request statuses | Yes (needed to retract a plan submission without deleting) |
| D-M0-5 | `request_task_review` / `return_task_for_correction` in M0.2c (not listed in 07) | Include; without them the screen cannot "pedir revisão/recusar" through a guarded route |
| D-M0-6 | `POST /projects/plans/{id}/approve` and baselines have no authorization for common projects | Out of M0 scope; open a separate hardening task |
| D-M0-7 | Who records what is published in each environment (`environment_releases`): the publishing task's report (`publish:` evidence) or Hephaestus' gate | Both write through one route; the gate is the authority for production |

## 12. What was not verified

- No code was run; all statements are from reading `develop@dcfe941`. Line numbers point at the decorator, definition or the first line of the cited block;
  they were re-checked once after writing.
- The `agt_` refusal of `POST /api/v1/tasks` / `POST /api/v1/planning-items` (§0.2) is inferred from
  `backend/app/main.py:200-232`; not exercised.
- The real count of existing `PlanBaseline` rows and their projects (04 mentions 1) was not queried —
  no database access in this task.
- Whether any live job writes `TaskExecution.status='completed'` (which M0.6a stops accepting for new
  `done` transitions) beyond the paths listed was checked by grep only.
- Host-bridge behavior for a git ancestry check (`publish` conflict, screen spec §5) is designed, not
  probed.
- Side observation (not fixed here): `RequireAuthMiddleware` admits the bridge token for paths ending
  in `/reprocess` [backend/app/main.py:285], but the route is `POST /api/v1/demands/{id}:reprocess`
  [backend/app/api/routes/demand.py:687] (colon, not slash), so the carve-out appears not to match. Not exercised.
