# Screen: Projects

## Route & Purpose

- `frontend/src/App.tsx:39` registers `<Route path="projects" element={<ProjectPage />} />` — list view, reachable at `/projects`.
- **No `/projects/:id` route is registered.** `frontend/src/pages/project/[id].tsx` (the detail view) exists on disk and is fully implemented, but `App.tsx` never mounts it. Compare with every other domain (e.g. `product/:id`, `pipeline/:id`, `tasks/:id` at `App.tsx:38,41,45`), all of which have a matching detail route — Project is the one domain missing it. The `index.tsx` list cards link to `/projects/${project.id}` (`index.tsx:148`), so today that link 404s (falls through to no matching route).
- Purpose (per the list page's own subtitle, `index.tsx:58`): "Bounded initiatives linked to a product version, with scope, plan, and baseline." The screen registers `Project` entities and (intended to) surface their `ProjectPlan` → `PlanBaseline` → `ChangeRequest` chain.

## Components

| File | Role |
|---|---|
| `frontend/src/pages/project/index.tsx` | List view: fetches all projects, renders a create form inline (toggle), a grid of project cards with status badge, linked product-version id, "View details" link, and delete button. |
| `frontend/src/pages/project/[id].tsx` | Detail view (**unreachable**, see above): would show project header/status, a "Project plan" card (scope, dates, estimated cost, baselined badge), a "Product version" card (raw id), and a static "Change requests" placeholder card. |
| `frontend/src/pages/project/ProjectForm.tsx` | Shared create form (react-hook-form + zod). Fields: name, description, product_version_id (free-text UUID input), status (select). Used only for create in `index.tsx`; no edit usage found anywhere. |
| `frontend/src/hooks/useProject.ts` | TanStack Query hooks + zod schemas for the Project domain (see below). |

## Data & API Calls

| Data shown | Source hook | Backend endpoint | Method |
|---|---|---|---|
| Project list (cards) | `useProjects()` | `/api/v1/projects` | GET |
| Single project (detail page, unreachable) | `useProject(id)` | `/api/v1/projects/{project_id}` | GET |
| Create project | `useCreateProject()` | `/api/v1/projects` | POST |
| Update project (defined, **never called** from any component) | `useUpdateProject(id)` | calls `apiClient.put(/api/v1/projects/{id})` | PUT — **but backend only exposes `PATCH /{project_id}`** (`backend/app/api/routes/project.py:91`); this hook would fail if ever invoked |
| Delete project | `useDeleteProject()` | `/api/v1/projects/{project_id}` | DELETE |

No hook exists for `ProjectPlan`, `PlanBaseline`, or `ChangeRequest` even though the backend fully supports them (`backend/app/api/routes/project.py`):
- `POST/GET /api/v1/projects/{project_id}/plans`, `GET/PATCH /api/v1/projects/plans/{plan_id}`, `POST /api/v1/projects/plans/{plan_id}/approve`, `DELETE /api/v1/projects/plans/{plan_id}`
- `POST/GET /api/v1/projects/{project_id}/baselines`, `GET /api/v1/projects/baselines/{baseline_id}`
- `POST/GET /api/v1/projects/{project_id}/change-requests`, `GET/PATCH /api/v1/projects/change-requests/{cr_id}`

None of these are wired into `useProject.ts` or any component — the frontend has zero ability to create/approve a plan, create a baseline, or create/decide a change request.

## Actions Available

- **Create project** — toggled inline form on the list page (`index.tsx:61,76-80`); submits name/description/product_version_id/status via `useCreateProject`. On success the form closes (`onSuccess: () => setShowForm(false)`, `index.tsx:47`).
- **Delete project** — trash icon button per card (`index.tsx:153-161`), calls `useDeleteProject().mutate(project.id)` with no confirmation dialog.
- **View details** — link to `/projects/{id}` (`index.tsx:147-152`) — currently dead due to the missing route (see Route & Purpose).
- No update/edit action is exposed anywhere in the UI for a project (despite `useUpdateProject` existing).
- No actions exist for plan approval, baselining, or change-request creation/decision — the (unreachable) detail page only renders a placeholder sentence for change requests ("Change request management is available once a baseline exists for this project," `[id].tsx:117-119`) with no button or form behind it.

## States

- **Loading**: list page shows a centered spinner + "Loading projects…" (`index.tsx:90-95`); detail page shows the equivalent "Loading project…" (`[id].tsx:19-24`).
- **Error**: list page shows a destructive-bordered card with the thrown error message (`index.tsx:97-104`); detail page has the same pattern (`[id].tsx:26-33`). Both read `(error as Error)?.message`, assuming `apiClient` always throws an `Error`.
- **Empty**: list page shows a dedicated empty state (folder icon, "No projects yet", CTA button) when `projects.length === 0` (`index.tsx:106-122`). No equivalent empty state is needed on the detail page (a project either exists or 404s into the error state).
- **Create-form submit error**: inline error text under the form if `createProject.isError` (`index.tsx:81-85`).
- Detail page has no handling for the case where `project` is `undefined` but `isLoading`/`isError` are both false (e.g., 404 with no error thrown) — it would just render nothing inside the conditional block.

## Business Rules Surfaced Here

- **None of the Planning rules (BUSINESS_RULES.md §3) are actually surfaced in the UI today**, despite the detail page's intent:
  - §3 Rule 1 ("Approved planning becomes baseline") — not exposed; no UI to approve a plan or create a baseline.
  - §3 Rule 2 ("Post-baseline changes require a Change Request") — not exposed; no UI to attempt a direct plan edit or to register a change request, so the 422 rejection in `update_project_plan` (`backend/app/api/routes/project.py:151-167`) is never reachable from this screen.
  - §3 Rule 3 (Change Request impact flags) — not exposed; no change-request form exists in the frontend at all.
- **Governance Rule §7.3** (Project status fixed set, added this session) is partially surfaced: the create form's status `<Select>` is driven by `PROJECT_STATUSES` (`useProject.ts:13-19`), matching the backend `CheckConstraint`/Pydantic validator (`backend/app/db/models/project.py:41`, `backend/app/api/schemas/project.py:32-36`). The list page also renders the status as a colored badge (`index.tsx:131-133`). However the *detail* page's badge is unreachable (route missing), and there is no UI surfacing of `ProjectPlan.status` or `ChangeRequest.status` fixed sets at all.
- The PRD/CLAUDE.md traceability invariant (Project ← ProductVersion FK) is partially surfaced: both list and (unreachable) detail pages display the raw `product_version_id` UUID rather than a resolved product/version name — there is no lookup/join to the Product domain on this screen.

## Dependencies

- **Project** (`backend/app/db/models/project.py`) — primary entity for this screen.
- **ProductVersion** (`backend/app/db/models/product.py`) — required FK target (`projects.product_version_id`); referenced only by raw UUID, never resolved to a human-readable name on this screen.
- **ProjectPlan**, **PlanBaseline**, **ChangeRequest** — modeled in the domain and fully supported by the backend router, but not actually fetched or rendered with live data on this screen (the detail page's plan card reads a `project.plan` field that the backend never returns — see Notes).

## Notes / Improvement Opportunities

- **Detail route is not registered.** `frontend/src/pages/project/[id].tsx` exists and is referenced by the list page's "View details" link (`index.tsx:148`), but `frontend/src/App.tsx` has no `<Route path="projects/:id" .../>` (compare lines 38/41/45/47/49/51 for every sibling domain). The file is effectively dead code today; either add the route or remove the file/link.
- **`ProjectOut` has no nested `plan` field**, but the frontend's `projectSchema` declares `plan: projectPlanSchema.nullable().optional()` (`frontend/src/hooks/useProject.ts:62-71`) and `[id].tsx:59-90` renders `project.plan.scope_summary` / `.target_date` / `.is_baselined` / `.estimated_cost`. `backend/app/api/schemas/project.py:58-64` (`ProjectOut(ProjectBase)`) only returns `id, name, description, product_version_id, owner, status, start_date, target_end_date, created_at, updated_at` — no `plan` key at all. Even if the route were registered, the "Project plan" card would always render its empty state ("No plan has been created for this project yet.") regardless of whether a plan exists, because `project.plan` is always `undefined`.
- **Field-name mismatch between frontend `ProjectPlan` zod schema and backend `ProjectPlanOut`.** Frontend expects `start_date`, `target_date`, `is_baselined` (boolean) (`useProject.ts:27-37`); backend actually returns `estimated_start_date`, `estimated_end_date`, and `status` (string enum `draft|approved|baselined|superseded`, see `backend/app/db/models/project.py` and `docs/DATA_MODEL.md` §3.2). Any future wiring of a real plan-fetch hook needs to fix this schema, not just add the missing endpoint call.
- **`useUpdateProject` calls `apiClient.put`, but the backend only exposes `PATCH /api/v1/projects/{project_id}`** (`backend/app/api/routes/project.py:91`, decorated `@router.patch`, no `@router.put` anywhere in the file). The hook (`useProject.ts:126-135`) would fail with a 405/404 if ever called — and it is in fact never called from any component, so this bug is currently latent/dormant.
- **`product_version_id` is required server-side** (`ProjectBase.product_version_id: uuid.UUID`, no default, `backend/app/api/schemas/project.py:26`) but the frontend form schema treats it as optional free text (`projectCreateSchema`, `useProject.ts:76-81`) and `index.tsx:44` explicitly converts an empty string to `undefined` before posting. Submitting the create form with that field blank will produce a 422 from the backend with no field-level guidance in the form (only a generic top-level error message, `index.tsx:81-85`).
- **`product_version_id` is a raw free-text UUID input** (`ProjectForm.tsx:67-72`) — no dropdown/typeahead against the Product domain, so a user must already know the target version's UUID. Same issue on display: both list and detail show the raw UUID instead of a resolved product/version label (`index.tsx:140-144`, `[id].tsx:100-104`).
- **Delete has no confirmation dialog** — clicking the trash icon (`index.tsx:153-161`) immediately calls the delete mutation. Given a project cascades to plans/baselines/change requests/tasks via the domain chain, this is a higher-blast-radius action than most other "delete" buttons in the app and arguably warrants a confirm step.
- **No edit/update UI** exists anywhere despite `useUpdateProject` being defined — status changes (e.g. `planned → active`) have no path through this screen today.
- **Change Request section on the (unreachable) detail page is entirely static placeholder text**, not data-driven (`[id].tsx:109-121`) — it neither lists existing change requests nor offers a way to create one, even though the backend supports both.
- **Owner, start_date, target_end_date fields** (present on the `Project` model/schema, `backend/app/db/models/project.py`) are not shown anywhere on this screen (list cards or detail page), nor collected by `ProjectForm`.
