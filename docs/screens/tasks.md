# Screen: Tasks

## Route & Purpose

Routes: `/tasks` (list) and `/tasks/:id` (detail) — `frontend/src/App.tsx:44-45`:
```
<Route path="tasks" element={<TaskPage />} />
<Route path="tasks/:id" element={<TaskDetailPage />} />
```
Components: `frontend/src/pages/task/index.tsx` (list) and `frontend/src/pages/task/[id].tsx` (detail), imported at `App.tsx:12-13`.

Purpose: manage `ProjectTask` rows — the planned units of work split out from a `PlanningItem` (Backlog domain) and tracked through assignment to an Agent/SubAgent and execution attempts (`TaskExecution`). The list view supports create/delete and a flat table of all tasks; the detail view is read-only and surfaces a single task's linkage (project, planning item, parent task, schedule/cost) plus its full execution history. There is no edit screen/affordance — the only mutations exposed in the UI are create (list) and delete (list); no `TaskForm` is reused on the detail page, and `useUpdateTask` (defined in the hook) is never called from either page.

## Components

| File | Role |
|---|---|
| `frontend/src/pages/task/index.tsx` | List page. Renders a "New task" toggle button, an inline create form (`TaskForm`), loading/error/empty states, and a table of all tasks with status/priority badges, due date, execution count, and per-row View/Delete actions. |
| `frontend/src/pages/task/[id].tsx` | Detail page. Renders task title/description/status/priority, three summary cards (Project, Planning item, Schedule & cost — all showing raw IDs, not resolved names), and a Task Executions table (executor, outcome, started/completed timestamps, actual cost, evidence link). Entirely read-only — no buttons to create an assignment, start an execution, or change status. |
| `frontend/src/pages/task/TaskForm.tsx` | Shared create form component (used only from the list page). Plain `react-hook-form` + Zod-resolved fields: title, description, project ID (free-text input), planning item ID (free-text input), parent task ID (free-text input), due date, status select, priority select, estimated cost. |
| `frontend/src/hooks/useTask.ts` | TanStack Query hooks + Zod schemas for the Task domain (`ProjectTask`, `TaskExecution`, `TaskDependency`, `TaskRequiredSkill`, `TaskAssignment` types are declared here, but only `ProjectTask`/`TaskExecution` are actually fetched/rendered by either page). |
| `frontend/src/components/ui/{button,card,table,badge,input,label,textarea,select}.tsx` | shadcn/ui primitives used throughout both pages and the form. |

## Data & API Calls

| Data shown | Source hook | Backend endpoint | Method |
|---|---|---|---|
| List of all tasks (title, status, priority, due date, execution count) | `useTasks()` (`useTask.ts:144-149`) | `/api/v1/tasks` | GET |
| Single task detail (title, description, status, priority, project_id, planning_item_id, parent_task_id, due date, estimated cost, nested `executions[]`) | `useTask(id)` (`useTask.ts:151-157`) | `/api/v1/tasks/{id}` | GET |
| Task executions table on detail page | rendered from `task.executions` nested in the `useTask(id)` response — **no separate fetch**; `GET /api/v1/tasks/{id}/executions` exists on the backend but is never called from the UI | (n/a — embedded) | — |
| Create task (list page form submit) | `useCreateTask()` (`useTask.ts:159-167`) | `/api/v1/tasks` | POST |
| Delete task (list page row action) | `useDeleteTask()` (`useTask.ts:180-188`) | `/api/v1/tasks/{id}` | DELETE |
| *(declared but unused by any page)* `useUpdateTask(id)` (`useTask.ts:169-178`) | calls `apiClient.put` | `/api/v1/tasks/{id}` | **PUT — see Notes; backend only exposes PATCH** |

## Actions Available

- **New task** (list page, `index.tsx:83-86`) — toggles the inline `TaskForm` card open/closed.
- **Create task** (`TaskForm` submit inside the toggled card) — calls `useCreateTask`, closes the form card on success (`index.tsx:57-71`). Shows the raw error message inline on failure (`index.tsx:103-107`).
- **Cancel** (form) — closes the create card without submitting.
- **View** (list row, `index.tsx:189-194`) — navigates to `/tasks/:id`.
- **Delete** (list row trash icon, `index.tsx:195-203`) — calls `useDeleteTask` immediately, no confirmation dialog; button disabled while any delete is pending.
- **Back to tasks / Back to list** (detail page, two links to `/tasks`) — navigation only.
- Detail page evidence link ("View", `[id].tsx:187-198`) — opens `execution.evidence_url` in a new tab when present; otherwise renders a plain dash.

No UI affordance exists to: assign a task to an agent/sub-agent, start or update a `TaskExecution`, add a `TaskDependency`, attach a `TaskRequiredSkill`, or change a task's status (including marking it `done`). All of those backend endpoints exist (`backend/app/api/routes/task.py`) but have no calling code anywhere in `frontend/src/pages/task/` or `frontend/src/hooks/useTask.ts`.

## States

**List page (`index.tsx`):**
- Loading: spinner + "Loading tasks…" (`index.tsx:112-117`), shown only while the form card is not handling its own pending state.
- Error: destructive card with the raw error message (`index.tsx:119-126`).
- Empty: dedicated card with icon, "No tasks yet" copy, and a "New task" CTA (`index.tsx:128-144`).
- Success: table of tasks (`index.tsx:146-212`).
- Create-form submit error shown inline under the form, separate from the page-level error state (`index.tsx:103-107`).

**Detail page (`[id].tsx`):**
- Loading: spinner + "Loading task…" (`[id].tsx:51-56`).
- Error: destructive card with the raw error message (`[id].tsx:58-65`); this also fires for a 404 (task not found), which is not visually distinguished from a network/server error.
- Success: full detail layout (`[id].tsx:67-218`).
- No explicit "empty" state is needed/possible for a detail page (it's always either loading, error, or one task).
- Within the success state: "No project linked." / "No planning item linked." italic placeholders shown when `project_id`/`planning_item_id` is null (`[id].tsx:93-97, 107-111`); "No executions recorded yet for this task." when `executions` is empty/null (`[id].tsx:204-208`).

## Business Rules Surfaced Here

- **BUSINESS_RULES.md §6 Rule 2** ("A `ProjectTask` must reference an existing `PlanningItem`") — enforced server-side in `create_task`/`update_task` (`backend/app/api/routes/task.py:78-85, 128-138`), but **not surfaced in the create form's UX**: the field is a free-text "Planning item ID" input with no existence validation or picker, so a user only discovers the violation after submit, via the raw backend error string rendered at `index.tsx:103-107`.
- **BUSINESS_RULES.md §4 Rule 3 / §6.4.3** ("Every execution must have evidence") — visible only as a read effect on the detail page: completed/verified executions show an evidence link when `evidence_url` is set, but the screen has no execution-creation/update UI, so the rule itself is never *enforced* from this screen — only its result is *displayed*.
- **BUSINESS_RULES.md §4 Rule 4 / §6 Rule 5** ("Every task completion must be auditable" — `AuditEvent` written when a task transitions to `done`) — not surfaced at all; there is no status-change control on either page, and the backend's `done` status string (`TASK_STATUSES` in `backend/app/api/schemas/task.py:24`) doesn't even match the frontend's own status vocabulary (see Notes).
- **BUSINESS_RULES.md §4 Rule 1** ("Planned, assigned, and executed remain distinct states") — partially surfaced as read-only: the list/detail pages render whatever `status` string the backend returns, including `assigned`/`in_progress` values that the backend sets automatically on `TaskAssignment`/`TaskExecution` creation (`backend/app/api/routes/task.py:227-228, 422-423`). The screen has no way to *trigger* those transitions itself.
- **Dependency blocking (BUSINESS_RULES.md §6.2.9 pattern, applied at task granularity in `_ensure_dependencies_satisfied`, `backend/app/api/routes/task.py:174-188`)** — not surfaced anywhere in this screen; no dependency list/editor exists in the UI, and the detail page never fetches `GET /api/v1/tasks/{id}/dependencies`.

## Dependencies

- **PlanningItem** (Backlog domain) — required FK on `ProjectTask`; shown as a raw ID on the detail page, entered as a raw ID on the create form. No name/title resolution.
- **ProjectTask** — the primary entity for both pages.
- **TaskDependency** — modeled in `useTask.ts` (`taskDependencySchema`) but never fetched or rendered by either page.
- **TaskRequiredSkill** — modeled in `useTask.ts` (`taskRequiredSkillSchema`) but never fetched or rendered.
- **TaskAssignment** — modeled in `useTask.ts` (`taskAssignmentSchema`) but never fetched or rendered; the detail page has no "assigned to" section at all despite the backend tracking agent/sub-agent assignment.
- **TaskExecution** — fetched as a nested array inside the `ProjectTask` detail response and rendered in a dedicated table on the detail page; this is the one secondary entity actually visible in the UI.
- **Agent / SubAgent** (Agent domain) — referenced only indirectly, as `execution.executor_id`/`executor_type` strings in the executions table; no agent name/profile lookup or link.
- **Skill** (Agent domain) — not surfaced at all on this screen.
- **Project** (Project domain) — `project_id` is shown/collected as a raw ID, but see Notes: this field does not exist in the backend's `ProjectTask` model/schema at all.

## Notes / Improvement Opportunities

**P1 — `TaskForm` planning_item_id field exists but is a raw-text input with no validation against real data, and `project_id` is dead weight the backend silently drops.**

- `TaskForm` **does** have a `planning_item_id` field: a plain `<Input>` bound via `register("planning_item_id")` at `frontend/src/pages/task/TaskForm.tsx:79-89`, labeled "Planning item ID" with placeholder "uuid of the source planning item". So the P1 risk framed in the task brief — "does the form even have the field the backend now requires" — is **not** the issue; the field is present and is sent in the create payload (`frontend/src/pages/task/index.tsx:57-66`, `planning_item_id: values.planning_item_id || undefined`).
- The real gap: it is a **free-text UUID box, not a picker** — there is no dropdown/search against existing `PlanningItem` rows (unlike, e.g., what a proper relational picker would do), so a user must already know (or copy-paste) a valid planning item UUID. Since `backend/app/api/routes/task.py:78-85` (`create_task`) now 400s if `planning_item_id` doesn't resolve to an existing `PlanningItem`, and the Zod schema (`taskCreateSchema` in `useTask.ts:111-124`) treats `planning_item_id` as optional (`z.string().optional().or(z.literal(""))`) with no client-side requirement, **submitting the form with the field left blank will pass client-side validation and then fail at the backend with a 400**, surfaced only as the raw error string `"Failed to create task: ..."` at `index.tsx:103-107`. There is no inline field-level error guiding the user to fill it in, and no UUID-format validation either (a non-UUID string will fail Pydantic's `uuid.UUID` coercion with a less friendly 422).
- **`project_id` is a phantom field.** `TaskForm` collects it (`TaskForm.tsx:71-77`, "Project ID") and `useTasks`'s create payload sends it, and `projectTaskSchema`/`taskCreateSchema` in `useTask.ts` both declare a `project_id` column — but `backend/app/db/models/task.py`'s `ProjectTask` model has **no `project_id` column at all** (only `planning_item_id` and `parent_task_id`), and `ProjectTaskCreate`/`ProjectTaskOut` in `backend/app/api/schemas/task.py` have no `project_id` field either. Since none of the Pydantic schemas set `extra="forbid"`, FastAPI silently ignores the field on POST — it is never persisted, never returned, and the detail page's "Project" card (`[id].tsx:87-99`) will always show "No project linked." for every task created through this form. This looks like a leftover from an earlier schema iteration and should either be removed from the form/hook or wired to a real backend column.

**Other findings (non-P1):**

- **Status vocabulary mismatch between frontend and backend.** Frontend `TASK_STATUSES` (`useTask.ts:21-28`) is `planned | assigned | in_progress | blocked | completed | cancelled`. Backend `TASK_STATUSES` (`backend/app/api/schemas/task.py:24`) is `planned | assigned | in_progress | blocked | done | cancelled` — the terminal state is `done`, not `completed`. The create form's status `<Select>` (`TaskForm.tsx:115-122`) offers `"completed"` as an option, which the backend's `ProjectTaskUpdate` validator (`backend/app/api/schemas/task.py:71-79`) will reject as not in `TASK_STATUSES` (no `ProjectTaskCreate.status` field exists at all — see next point). The list/detail pages' `STATUS_VARIANT` maps also key off `"completed"` (`index.tsx:37`, `[id].tsx:24`), so a real `done` status returned by the backend would render with the unstyled fallback badge variant (`?? "outline"`).
- **`ProjectTaskCreate` (backend) has no `status` field at all** (`backend/app/api/schemas/task.py:54-55`) — only `ProjectTaskUpdate` does. The frontend create form collects and submits a `status` value regardless (defaulting to `"planned"`), which is silently dropped by the backend on create (same "extra field ignored" behavior as `project_id`/`due_date` below). Every newly created task is `planned` server-side no matter what the form's status select says.
- **`due_date` is another phantom field.** The form collects it and `ProjectTask`/`taskCreateSchema` (frontend) declare it, but the backend model only has `planned_start_date`/`planned_end_date` (date range) plus `started_at`/`completed_at` (timestamps) — no single `due_date` column anywhere in `backend/app/db/models/task.py` or `backend/app/api/schemas/task.py`. Same silent-drop behavior; the list table's "Due date" column and detail page's "Due date" field will always show "—" for tasks created via this screen.
- **`useUpdateTask` is dead code from this screen's perspective** — defined in `useTask.ts:169-178` and calls `apiClient.put(...)`, but (a) no page imports/calls it, and (b) the backend route file defines only `@router.patch("/{task_id}", ...)` (`backend/app/api/routes/task.py:120`), not PUT — so even if a future page wired this hook up, it would 405 against the current backend. The status-change/edit UX for tasks does not exist yet at any layer of this screen.
- **No name resolution for any linked entity** — `project_id`, `planning_item_id`, and `parent_task_id` are all rendered as raw UUID strings on the detail page (`[id].tsx:94, 108, 133`) rather than resolved titles, making the screen hard to use without a separate lookup.
- **No confirmation on delete** (`index.tsx:195-203`) — clicking the trash icon fires the DELETE mutation immediately.
- **Detail page never calls** `GET /api/v1/tasks/{id}/executions`, `/dependencies`, `/required-skills`, or `/assignments` — all four sub-resource list endpoints exist on the backend (`backend/app/api/routes/task.py:235-245, 343-352, 389-397, 430-438`) but only the executions array embedded in the main task fetch is used; dependencies, required skills, and assignments have zero visibility on this screen even though they are core to the Task domain's traceability model per `docs/DATA_MODEL.md` §3.5.
- **404 vs. generic error not distinguished** on the detail page — both render the same destructive card with the raw `error.message` (`[id].tsx:58-65`).
