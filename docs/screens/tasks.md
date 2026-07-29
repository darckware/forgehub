# Screen: Tasks (Execution)

## Route & Purpose

Routes: `/tasks` (list, labeled "Execution" in the sidebar) and `/tasks/:id` (detail) — `frontend/src/App.tsx`:
```
<Route path="tasks" element={<TaskPage />} />
<Route path="tasks/:id" element={<TaskDetailPage />} />
```
Components: `frontend/src/pages/task/index.tsx` (list) and `frontend/src/pages/task/[id].tsx` (detail).

Purpose: manage `ProjectTask` rows — the planned units of work split out from a `PlanningItem` (or a `ChangeRequest`) and tracked through assignment to an Agent/SubAgent and execution attempts (`TaskExecution`). The list view supports create/delete and a flat table of all tasks (filterable by project); the detail view shows the task's linkage (project, planning item, schedule/cost), its dependencies and required skills, the Governed CLI execution card (assignment + dispatch pointer), and its full execution history. There is still no in-place status-change control outside of assignment/execution side effects — a task's own `status` field can only be changed by those, not typed directly (by design: `PATCH` rejects `status: "ready"`, that value is set only by `ActivateExecutionWave`). (Kanboard sync — push/pull card and `sync-kanboard`/`pull-kanboard` endpoints — was removed 2026-07-28 when Kanboard was discontinued; task management and agent-to-agent dispatch are now native via ForgeHub's own MCP server, surfaced by the Messages component, see `CLAUDE.md`.)

## Components

| File | Role |
|---|---|
| `frontend/src/pages/task/index.tsx` | List page. "New task" toggle, inline create form (`TaskForm`), a project filter dropdown, loading/error/empty states, and a table of all tasks with status/priority badges, due date, execution count, and per-row View/Delete actions. A fixed "ForgeRouter Anthropic adapter task" card with a copy-to-clipboard prompt sits above the table (unrelated to any specific task — a canned prompt for a specific piece of infra work). |
| `frontend/src/pages/task/[id].tsx` | Detail page. Task title/description/status/priority, three summary cards (Project, Planning item, Schedule & cost), `TaskDependenciesCard`, `TaskAutomationCard` (assignment + governed dispatch pointer), and the Task Executions table (executor, outcome, timestamps, actual cost, evidence link). |
| `frontend/src/pages/task/TaskForm.tsx` | Shared create/edit form (used by the list page and reused inline by the Backlog page's per-planning-item task rows). Fields: title, description, a **Project filter** (local UI state only — narrows the Planning item / Change request pickers below, never submitted; a task has no `project_id` column of its own), planning item picker, change request picker, parent task picker, due date (maps to the backend's `planned_end_date`), status select, priority select, estimated cost, governance policy. |
| `frontend/src/components/TaskAutomationCard.tsx` | "Governed CLI execution" card: lists eligible project memberships (`GET /orchestration/tasks/{id}/eligible-memberships`, computed from required skills + membership status/validity) with reasons for ineligible ones, lets you create a `TaskAssignment`, and shows automated execution attempts + their loop-policy reviews. The actual dispatch button is permanently disabled — legacy direct dispatch (`POST /orchestration/tasks/{id}/dispatch`) was retired (410 Gone) by ER-RUN-01; the button points users at Planning > Execution Release (ExecutionWave → Work Package → `POST /work-packages/{id}:dispatch`) instead. |
| `frontend/src/components/TaskDependenciesCard.tsx` | Added 2026-07-16. Lists/creates `TaskDependency` rows (with delete) and `TaskRequiredSkill` rows (create + list only — the backend has no delete endpoint for this sub-resource). Required skills here are what `TaskAutomationCard`'s eligibility check reads. |
| `frontend/src/hooks/useTask.ts` | TanStack Query hooks + Zod schemas for the Task domain. |
| `frontend/src/hooks/useOrchestration.ts` | Hooks for `TaskAssignment`, eligible memberships, dispatch (legacy, 410), and execution reviews — consumed by `TaskAutomationCard`. |

## Data & API Calls

| Data shown | Source hook | Backend endpoint | Method |
|---|---|---|---|
| List of all tasks (title, status, priority, due date, execution count) | `useTasks()` | `/api/v1/tasks` (optionally `?project_id=`) | GET |
| Single task detail | `useTask(id)` | `/api/v1/tasks/{id}` | GET |
| Task executions table on detail page | rendered from `task.executions` nested in the `useTask(id)` response; `TaskAutomationCard` separately calls `useTaskExecutions` for its own "Automated runs" section | `/api/v1/tasks/{id}/executions` | GET |
| Task dependencies (`TaskDependenciesCard`) | `useTaskDependencies(id)` / `useCreateTaskDependency` / `useDeleteTaskDependency` | `/api/v1/tasks/{id}/dependencies[/{depId}]` | GET / POST / DELETE |
| Required skills (`TaskDependenciesCard`) | `useTaskRequiredSkills(id)` / `useCreateTaskRequiredSkill` | `/api/v1/tasks/{id}/required-skills` | GET / POST (no DELETE on the backend) |
| Task assignments + eligibility (`TaskAutomationCard`) | `useTaskAssignments` / `useCreateTaskAssignment` / `useEligibleMemberships` | `/api/v1/tasks/{id}/assignments`, `/api/v1/orchestration/tasks/{id}/eligible-memberships` | GET / POST / GET |
| Create task | `useCreateTask()` | `/api/v1/tasks` | POST |
| Update task | `useUpdateTask(id)` | `/api/v1/tasks/{id}` | PATCH |
| Delete task | `useDeleteTask()` | `/api/v1/tasks/{id}` | DELETE |

## Actions Available

- **New task** (list page) — toggles the inline `TaskForm` card.
- **Create task** — calls `useCreateTask`, closes the card on success; raw error message shown inline on failure.
- **Project filter** (list page dropdown) — client-side filter on the (now backend-derived) `task.project_id`.
- **View / Delete** (list row) — navigate to `/tasks/:id`, or delete immediately (no confirmation dialog).
- **Add/remove dependency, add required skill** (`TaskDependenciesCard`) — see Data & API Calls.
- **Assign an eligible member, review an automated execution** (`TaskAutomationCard`).
- Detail page evidence link — opens `execution.evidence_ref`/`evidence_url` in a new tab when present.

Still missing at this screen: no direct "mark done" control (by design, see Purpose) and no inline task edit UI on the detail page itself (editing happens through the list page's per-row form, or the Backlog page's embedded `TaskForm` for a planning item's tasks).

## States

**List page:** loading spinner, destructive error card, empty-state card with CTA, success table; create-form submit error shown inline under the form.

**Detail page:** loading spinner; destructive error card (404 and other errors render the same way — not visually distinguished); success layout with per-card empty states ("No project linked.", "No planning item linked.", "No dependencies…", "No skill requirements…", "No executions recorded yet for this task.").

## Business Rules Surfaced Here

- **Traceability** ("a `ProjectTask` must reference an existing `PlanningItem` or `ChangeRequest`") — enforced server-side in `create_task`; the form's Planning item / Change request pickers are real dropdowns (not free-text), filtered by the Project selector, but there's still no inline field-level guidance if both are left empty (only the raw 400 message).
- **Dependency blocking** (a task can't go `done` while a dependency isn't itself `done`, `_ensure_dependencies_satisfied`) — now surfaced and editable via `TaskDependenciesCard` (added 2026-07-16; previously invisible).
- **Eligibility via required skills** (`TaskAutomationCard`'s eligible-memberships check) — required skills are now editable from the same detail page (`TaskDependenciesCard`) instead of only visible as an opaque skill UUID in an ineligibility reason string.
- **Every execution must have evidence** — visible as a read effect (evidence link) on completed/verified executions; the screen still has no execution-creation UI of its own (execution creation goes through the governed Work Package dispatch flow, Planning > Execution Release).
- **`status: "ready"` is set only by ActivateExecutionWave** — `PATCH` rejects a client-supplied `"ready"` value; the list/detail status badges render it as any other read-only state once the backend sets it.

## Dependencies

- **PlanningItem** (Backlog domain) — optional-but-usually-set FK; the Project filter in `TaskForm` scopes the picker to one project's planning items.
- **ChangeRequest** (Project domain) — the other valid traceability source; scoped the same way.
- **Project** — a task has no `project_id` column of its own. The backend derives it per-request (`_attach_project_ids` in `routes/task.py`, from whichever of planning_item/change_request the task traces to) and returns it as `ProjectTaskOut.project_id`; this is what the list page's project filter and the detail page's "Project" card actually read. Fixed 2026-07-16 — before that, both the create form and the frontend types carried a `project_id` field that the backend silently discarded, so the filter and the "Project" card were permanently broken (always "No project linked.").
- **TaskDependency** / **TaskRequiredSkill** — fully surfaced via `TaskDependenciesCard` (2026-07-16).
- **TaskAssignment** — fully surfaced via `TaskAutomationCard` (agent eligibility + assignment; predates this doc's last rewrite).
- **TaskExecution** — rendered both as the nested array on the main task fetch and via `TaskAutomationCard`'s own fetch (automated runs + loop-policy reviews).
- **Agent / SubAgent** (Agent domain) — resolved to names in `TaskAutomationCard`'s eligibility list; still shown as raw executor references in the plain executions table.
- **Skill** (Agent domain) — resolved to names in `TaskDependenciesCard`'s required-skills picker/list.

## Notes / Improvement Opportunities

- **`status` has no `ProjectTaskCreate` field at all** — only `ProjectTaskUpdate` has it. The create form still shows a status select (defaulting to "planned"), which the backend silently ignores on create; every new task starts `planned` regardless of what the form's select shows. Not fixed in the 2026-07-16 pass (lower impact than `project_id`/`due_date`, since "planned" is the correct starting state anyway) — worth either removing the status select from the create path or wiring a real create-time status if that's ever needed.
- **No confirmation on delete** (list row trash icon) — fires the DELETE mutation immediately.
- **404 vs. generic error not distinguished** on the detail page — both render the same destructive card with the raw error message.
- **No name resolution for `parent_task_id`** on the detail page's Schedule & cost card (shown via a lookup against the full task list, which works but is O(n) client-side and silently shows a truncated UUID if the task list hasn't loaded yet).
