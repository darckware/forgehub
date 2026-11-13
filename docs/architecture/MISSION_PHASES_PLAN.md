# Mission phases (2026-11-12)

Marcelo: "para simplificar posso associar cada fase a um projeto ... a criação da
estrutura da aplicação sem nenhuma regra de negócio, somente para validação da
estrutura de navegação e design system ... uma fase de somente as telas sem
código para homologar o escopo do sistema" and "cada projeto pode ter vários
planejamentos e em cada planejamento o conjunto de tarefas organizadas
sequencialmente". Decisions he confirmed ("concorda"):

1. Planning items inside one phase may run in parallel; the tasks inside one
   planning item always run in sequence.
2. Every phase ends with a homologation by an **external** agent (claude/codex/agy)
   that is neither an executor nor a reviewer of that phase's tasks, and then
   **Marcelo's approval** of the phase.
3. Phases run strictly in order: no task of phase N is dispatched until every
   phase before N is approved.

## Model

```
Mission (Project project_type='mission' + project_missions)
 └─ Phase = mission_project_links row (mission -> executor project), ordered
     └─ Planning item (planning_items, ordered by position)  -- may run in parallel
         └─ Task (project_tasks, ordered by position)         -- always sequential
```

`mission_project_links` already exists (D-3, executor projects of a mission) and
`mission_scope_tasks` already includes executor projects' tasks, so a phase
reuses the whole mission machinery (baseline, dispatch guard, completion guard).

### Migration (down_revision `a3c5e7f9b1d2`)

`mission_project_links` gains:

| column | type | notes |
|---|---|---|
| `position` | int NOT NULL | 1-based, `UNIQUE (mission_project_id, position)` DEFERRABLE INITIALLY DEFERRED (reorder swaps) ; backfill = row_number by created_at |
| `name` | varchar(255) NOT NULL | backfill = executor project name |
| `objective` | text NULL | what the phase delivers and what it leaves out |
| `phase_status` | varchar(24) NOT NULL default `planned` | CHECK in `planned, in_progress, homologating, awaiting_approval, approved, returned` |
| `homologator_agent_id` | uuid FK agents NULL | |
| `homologation_demand_id` | uuid FK agent_demands NULL ON DELETE SET NULL | the Messages task sent to the homologator |
| `homologation_verdict` | varchar(16) NULL | `approved` / `rejected` |
| `homologation_summary` | text NULL | |
| `homologation_evidence` | text NULL | refs (git:/file:/url) as text |
| `homologated_at` | timestamptz NULL | |
| `decided_by` | varchar(150) NULL | Marcelo's username |
| `decided_at` | timestamptz NULL | |
| `decision_reason` | text NULL | required on return |

`planning_items.position` int NULL, `project_tasks.position` int NULL.

`PROJECT_AGENT_ROLES` gains `"homologation"`. Every CHECK built from that tuple
must be recreated in the migration (`ck_project_agent_memberships_role`, agents
`default_role`, `chat_channel_members.role`, the channel `role_required` one --
find their real names in `db/models/agent.py`, `db/models/channel.py`,
`db/models/orchestration.py`). `homologation` joins `NON_EXECUTOR_ROLES`
(`core/mission_plan.py`) and, like code roles, is only for runtimes in
`CODE_RUNTIMES` (members:apply in `api/routes/mission.py`).

## Rules

- **Editing phases** (create, rename, objective, reorder, delete) only while the
  mission is `draft` or `planning` and has no current baseline -> else 409
  `MISSION_PHASES_FROZEN`. Phases are part of the plan hash: add
  `phases: [(position, name, objective, executor_project_id)]` to
  `mission_content_part` (`core/plan_baseline.py`). Check existing baseline
  hash tests still pass (a mission with no phases must keep hashing the same:
  include the key only when there is at least one phase, or accept and update
  tests -- prefer the former).
- **Creating a phase** creates the executor Project in the same transaction
  (same product version as the mission, name `"<mission name> · Fase N · <name>"`,
  `working_directory_path` = the mission's), through `project.py`'s
  `build_project` the way `create_internal_project` does, and the link at
  `max(position)+1`. Audit `mission_phase_created`.
- **Deleting a phase** only when its project has no planning items or tasks
  (409 `PHASE_NOT_EMPTY`); removes link and project; renumbers positions.
  Audit.
- **Sequencing a planning item's tasks**: `tasks:sequence {task_ids:[...]}` must
  list exactly the planning item's non-cancelled tasks; sets `position` 1..n and
  replaces the finish_to_start dependencies *between tasks of that planning
  item* with the chain t1<-t2<-...<-tn (dependencies to tasks outside the item are
  kept). Refused (409 `TASK_IN_BASELINE`) when any of them is in a current
  baseline. Reordering planning items only sets `planning_items.position`.
  A new mission task created in a planning item that already has positioned
  tasks is not auto-chained; the plan check below catches it.
- **Plan checks** (`core/mission_plan.py` automatic checks at submission, and
  the draft_plan exit conditions in `core/mission.py`): `PHASES_MISSING` when
  the mission has no phase; `PHASE_OBJECTIVE_MISSING` per phase without
  objective; `TASKS_NOT_SEQUENCED` per planning item whose non-cancelled tasks
  (>1) don't all have a position and the full chain. Mission-level tasks
  outside any phase are allowed (keep current behavior) -- but report
  `TASK_OUTSIDE_PHASE` as a check item only when the mission has phases.
  Look at how existing checks/exit items are shaped and follow them; update
  the tests whose expected sets change.
- **Dispatch gate**: in `core/task_baseline_guard.py`'s
  `assert_task_baseline_current`, when the task's project is a phase of the
  governing mission at position N, every phase with position < N must be
  `approved`, else `TaskBaselineBlocked("PHASE_LOCKED", ...)` with the blocking
  phases. A phase `homologating`/`awaiting_approval`/`approved` also refuses
  dispatching its own tasks (`PHASE_CLOSED`); `returned` reopens it. The first
  successful dispatch of a phase task moves `planned`/`returned` ->
  `in_progress` (do it where the dispatch is committed, or lazily in the
  status read; pick the simplest correct place and say which).
- **active -> verifying** additionally requires every phase `approved`
  (`PHASES_NOT_APPROVED`).
- **Homologation request** `POST /missions/{id}/phases/{phase_id}:request-homologation
  {homologator_agent_id}` -- admin or the orchestrator (`_authorize_conduct`).
  Requires phase `in_progress`/`returned`/`planned` with every non-cancelled
  task closed (`TASK_CLOSED_STATUSES`, done/deployed); else 409
  `PHASE_TASKS_OPEN` listing them. Homologator: active agent with
  `runtime_type` in `CODE_RUNTIMES`, an active `homologation` membership in the
  mission project, and not the executor nor a reviewer of any of the phase's
  tasks (reuse how `request_task_review`/completion guard resolve executor and
  reviewers) -> 409 `HOMOLOGATOR_NOT_INDEPENDENT` / 422 `HOMOLOGATOR_NOT_EXTERNAL`
  / 409 `HOMOLOGATOR_NOT_MEMBER`. Sends one Messages Task (same shape as
  `request_task_review`: from orchestrator, `fixed_agent=True`,
  `working_path` = mission working directory, no `task_execution_id`) whose
  body states: the phase objective, what is out of scope, the planning items
  and their numbered tasks with evidence refs, that it must test the delivery
  against the objective, and that it must answer through the MCP tool
  `report_phase_homologation` (approved/rejected + summary + evidence).
  Status -> `homologating`. Audit.
- **Homologation report** `POST .../phases/{phase_id}:report-homologation
  {verdict, summary, evidence}` -- only the `agt_` of `homologator_agent_id`
  while `homologating` (403 otherwise, 409 wrong state). `approved` ->
  `awaiting_approval` plus a `Notification` (warning) "Fase N de <missão>
  homologada, aguardando sua aprovação" with a link to the mission page;
  `rejected` -> `returned` plus a Notification to Marcelo and a Messages Task to
  the orchestrator stating the homologator's findings so it can plan the
  corrections. Audit.
- **Marcelo's decision** `POST .../phases/{phase_id}:approve` and
  `:return {reason}` -- admin JWT only, phase `awaiting_approval`. Approve ->
  `approved` (`decided_by/at`); return -> `returned` with reason, plus a
  Messages Task to the orchestrator with the reason. Audit
  `mission_phase_approved` / `mission_phase_returned`. After approving phase N,
  notify the orchestrator (Messages Task) that phase N+1 is unlocked, or, if it
  was the last, that the mission can go to verifying.
- Every write uses `row_version` of the mission? No -- phases have their own
  state; use the phase's current `phase_status` as the guard and return 409
  `PHASE_STATE_CHANGED` when it moved. Agent writes take an `idempotency_key`
  like the other M0.2 routes (`core/command_receipts.py`) and sit behind
  `MISSION_TOOLS_ENABLED` for agents, exactly like `mission_task.py`.

## API (new `api/routes/mission_phase.py`, router prefix `/api/v1/missions`)

- `GET /{id}/phases` -- admin or active member: phases in order, each with
  status fields, homologator, executor project id/name, planning items in
  order, each with tasks in order (number, title, status, position, assignee
  name, depends_on numbers). Also expose it inside the board payload
  (`core/mission_board.py`) as `phases` so the page needs one query.
- `POST /{id}/phases`, `PATCH /{id}/phases/{phase_id}`, `DELETE /{id}/phases/{phase_id}`,
  `POST /{id}/phases:reorder {phase_ids}`,
  `POST /{id}/phases/{phase_id}/plannings:reorder {planning_item_ids}`,
  `POST /{id}/plannings/{planning_item_id}/tasks:sequence {task_ids}`,
  the homologation and decision routes above.
- Admin JWT or the orchestrator for the edits; middleware: check how
  `RequireAuthMiddleware` admits `agt_` on `/api/v1/missions/...` routes and
  follow the existing pattern.

## MCP (`app/mcp/factory_server.py`)

`list_mission_phases`, `create_mission_phase(project_id, name, objective)`,
`update_mission_phase`, `reorder_mission_phases`, `sequence_planning_tasks(planning_item_id, task_numbers or ids)`,
`request_phase_homologation(project_id, phase, homologator)`,
`report_phase_homologation(project_id, phase, verdict, summary, evidence)`.
Docstrings in the style of the existing mission tools, saying who may call
each and that the homologator must be external and independent.

## Frontend

- `components/missions/MissionPhases.tsx` (+ `useMissionPhasesViewModel` per
  the §21 standard) on the mission page above the executions board: a strip of
  numbered phases with status badges; each phase expands to its planning items
  (in order) and their numbered tasks with status. Admin, while
  draft/planning with no baseline: add phase (name + objective), edit, move
  up/down, delete (ConfirmDialog). Admin, phase `awaiting_approval`: shows the
  homologation summary/evidence and buttons "Aprovar fase" / "Devolver"
  (reason required). Mobile at 390px per CLAUDE.md rules.
- zod schema for `phases` in `useMissions.ts` board schema (optional, default
  `[]`), fixture update, i18n pt-BR/en/es under `missions.phases.*`.
- Tests: vitest for the component (render, add phase, approve/return).

## Tests (backend, `app/tests/test_mission_phases.py`)

Create/reorder/delete rules and freezing; tasks:sequence chain and keeping
outside deps; plan checks; dispatch gate PHASE_LOCKED/PHASE_CLOSED (call
`assert_task_baseline_current` directly like `test_task_baseline_guard.py`);
homologation request independence/external/member/open-task refusals; report by
the wrong agent; approve/return by admin only; verifying gate; role
`homologation` accepted in members:apply only for external runtimes.

## Decisions taken (implementation, 2026-11-12)

- **Migration `c7d9e1f3a5b8`** (down `a3c5e7f9b1d2`). **Legacy executor links
  are not phases** (review fix): `mission_project_links.is_phase` (bool, NOT
  NULL, default false); `position`/`name` are nullable, with
  `ck_mission_project_links_phase_fields` = `NOT is_phase OR (position IS NOT
  NULL AND name IS NOT NULL)`; the deferrable unique (mission, position) lets
  NULLs coexist. No backfill: existing links (and `POST /missions` with
  `executor_project_ids`) stay plain links. Only `POST /phases` creates
  `is_phase = true`, and every phase read, gate, hash part, plan check,
  rename, delete, board and `GET /phases` reads only those rows -- so a mission
  with only legacy links hashes exactly as before (tested against the
  pre-phases formula).
- **Locks follow phases.** A phase task's required skills and environment are
  locked outside `planning` like a mission task's (`_mission_owning` in
  `core/mission.py` resolves a phase project to its mission; a plain executor
  link does not).
- **Plan scope.** The draft_plan and auto_check exit conditions now read the
  tasks and memberships of the mission *and* of its phases (executor
  projects), as `plan_checks` already did; otherwise a mission whose work
  lives in phases would always fail `NO_TASKS`.
- **`TASK_OUTSIDE_PHASE`** appears only in the submission checks, as a check
  with the new status `warning` (`passed: true`, key `tasks_in_phases`); it
  is not an exit-condition item, since exit items always block. The phase
  items go in a `phases` check.
- **Phase start** is marked in `reserve_dispatch`, after every admission
  check passes and in the reservation's transaction (also for a review run
  of a phase task, which only happens while the phase is in progress).
- **Wrong phase state** is always 409 `PHASE_STATE_CHANGED` (with
  `phase_status` and the allowed ones), whether or not the caller sent
  `expected_phase_status`.
- **Idempotency.** Agents must send `idempotency_key` and need
  `MISSION_TOOLS_ENABLED` (422 `IDEMPOTENCY_KEY_REQUIRED`); for a person the key
  is optional (the screen sends none). `DELETE` takes it as a query parameter.
- **Creating a phase** also gives the orchestrator an active `coordinator`
  membership in the phase project (so it can staff it with
  `manage_project_members`); the project type is `creation`. Renaming,
  reordering and deleting keep each phase project's name as
  `"<mission> · Fase N · <name>"`. Deleting removes the project only when no
  other mission links it.
- **`plannings:reorder`** follows the phase freeze (`MISSION_PHASES_FROZEN`).
  `tasks:sequence` only refuses frozen tasks (`TASK_IN_BASELINE`), a terminal
  mission, a planning item outside the mission and phases (404), a task set
  that is not exactly the item's non-cancelled tasks (422 `TASK_SET_MISMATCH`)
  and a resulting cycle (409 `DEPENDENCY_CYCLE`). It removes every dependency
  between the listed tasks (any type) before writing the chain.
- **A phase with no non-cancelled task** blocks the plan
  (`PHASE_WITHOUT_TASKS`, draft_plan exit and the `phases` submission check),
  so a phase can never be stuck with nothing to homologate.
- **Homologation request** also refuses a phase with no non-cancelled task
  (409 `PHASE_EMPTY`) and an inactive/unknown agent (422
  `HOMOLOGATOR_NOT_ELIGIBLE`). Independence covers every assignment (any
  status), every execution's resolved executor and every review's reviewer of
  the phase's tasks; an agent and its sub-agents are one identity
  (`_agent_identity`, as in the completion guard).
- **Re-sending a homologation**: the same route with `replace: true` accepts a
  `homologating` phase (same or another homologator). The previous task is
  archived when it never started; a run dispatched, running, reserved or of
  unknown outcome refuses 409 `HOMOLOGATION_RUN_IN_FLIGHT`; a finished one is
  left as history. The audit's `replaced` records the previous homologator and
  task. MCP `request_phase_homologation(..., replace=True)`.
- **Project names**: renaming or renumbering re-checks that every new phase
  project name is free in the product version, ignoring the projects being
  renamed in the same call (so a swap works): 409
  `PROJECT_NAME_EXISTS_IN_VERSION`.
- **Report guards**: `:report-homologation` refuses a completed/cancelled
  mission (409 `MISSION_TERMINAL`) and a homologator whose `homologation`
  membership is no longer active (409 `HOMOLOGATOR_NOT_MEMBER`). The Messages task has `origin_type="task"` with no
  `origin_id` (so the phase gate it is closing never holds it), `project_id`
  = the phase project, `channel="factory"`, `channel_ref` = phase id. A new
  request clears the previous round's verdict and decision fields (the audit
  keeps the history).
- **Homologation report**: `approved` requires at least one evidence ref (422
  `EVIDENCE_REQUIRED`); evidence is stored one ref per line. A person (admin
  included) gets 403 `HOMOLOGATOR_ONLY`.
- **Messages to the orchestrator** (rejection, return, approval) are Tasks
  queued now with `fixed_agent=True` in the mission's working directory: from
  the homologator on a rejection, self-addressed (orchestrator →
  orchestrator) for Marcelo's decisions, since Marcelo has no agent id.
- **Notifications** carry the mission link (`/missions/<id>`) in the message
  text (the table has no link column); `event_key` =
  `mission-phase:<phase id>:<homologated|rejected>:<timestamp>`.
- **Read access** to `GET /phases` is admin or active member (as the spec
  says); the board's `phases` follows the board's own read rule.
- **Test database**: stamped at a foreign revision, so the DDL was applied by
  hand (idempotent) to match the migration: same NULLability, constraint and
  FK names (only the physical column order differs, `is_phase` last).
