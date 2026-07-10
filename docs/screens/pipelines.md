# Screen: Pipelines

## Route & Purpose

- `/pipeline` — list view (`frontend/src/pages/pipeline/index.tsx`): lists all `ProjectPipeline` rows across every project, lets the user create a new pipeline, and delete an existing one.
- `/pipeline/:id` — detail view (`frontend/src/pages/pipeline/[id].tsx`): read-only view of one pipeline's stages, each stage's required artifacts and gates, and dependency counts.

Registered in `frontend/src/App.tsx:8-9,40-41` and in the sidebar nav as "Pipelines" (`frontend/src/components/layout/Sidebar.tsx:60`, icon `GitBranch`).

Purpose, per the list page's own subtitle (`index.tsx:56-59`): "Delivery flow for each project: ordered stages, required artifacts, and approval gates that must pass before release."

## Components

| File | Role |
|---|---|
| `frontend/src/pages/pipeline/index.tsx` | List page: fetches all pipelines, renders create form toggle, grid of pipeline cards, delete action, loading/empty/error states. |
| `frontend/src/pages/pipeline/[id].tsx` | Detail page: fetches one pipeline by id, renders a `StageCard` per stage sorted by `order`, pipeline-level status/active badges. |
| `frontend/src/pages/pipeline/[id].tsx` (`StageCard`, lines 39-139) | Local sub-component (not exported, not reused elsewhere): renders one stage's name/order/status badge, stage type, approval/verification flags, required-artifacts checklist, gates checklist, and dependency count. |
| `frontend/src/pages/pipeline/PipelineForm.tsx` | Shared create form (react-hook-form + Zod resolver): name, project_id (raw UUID text input), pipeline_template_id (raw UUID text input, optional), status select, is_active checkbox. Used only by the list page (no edit/update usage found — see Notes). |
| `frontend/src/hooks/usePipeline.ts` | TanStack Query hooks (`usePipelines`, `usePipeline`, `useCreatePipeline`, `useUpdatePipeline`, `useDeletePipeline`) and the Zod schemas/types for `ProjectPipeline`, `PipelineStage`, `StageRequiredArtifact`, `StageGate`. |
| `frontend/src/components/ui/card.tsx`, `badge.tsx`, `button.tsx` | Generic shadcn/ui primitives used for layout/status pills/actions. |

No separate "create stage" / "create gate" / "create required artifact" UI exists anywhere in the frontend — those backend endpoints (`POST /api/v1/pipelines/{id}/stages`, `.../stages/{id}/gates`, `.../stages/{id}/required-artifacts`) have no calling code in `frontend/src/hooks/usePipeline.ts` or any page.

## Data & API Calls

| Data shown | Source hook | Backend endpoint | Method |
|---|---|---|---|
| List of all pipelines (name, status, is_active, project_id, stage count/completed count) | `usePipelines()` (`usePipeline.ts:133-138`) | `/api/v1/pipelines` | GET |
| Single pipeline detail (name, status, is_active, project_id, stages incl. nested required_artifacts/gates/dependencies) | `usePipeline(id)` (`usePipeline.ts:140-146`) | `/api/v1/pipelines/{id}` | GET |
| Create pipeline (from form) | `useCreatePipeline()` (`usePipeline.ts:148-156`) | `/api/v1/pipelines` | POST |
| Delete pipeline (list page trash icon) | `useDeletePipeline()` (`usePipeline.ts:170-178`) | `/api/v1/pipelines/{id}` | DELETE |
| Update pipeline | `useUpdatePipeline(id)` (`usePipeline.ts:158-168`) | `/api/v1/pipelines/{id}` | PATCH — **exported but never called from any page/component** (verified via grep: no `useUpdatePipeline(` call site outside the hook file itself) |

No request goes through `apiClient`'s Zod runtime validation — `usePipelines`/`usePipeline` call `apiClient.get<ProjectPipeline[]>(...)` / `apiClient.get<ProjectPipeline>(...)` (`usePipeline.ts:136,143`), which is a plain `fetch` + `JSON.parse` cast via TypeScript generics only (`frontend/src/lib/api.ts:45-72`, `96-106`). The exported Zod schemas (`projectPipelineSchema`, `pipelineStageSchema`, etc.) are never `.parse()`d against the live response anywhere in this screen — see Notes for the consequence.

## Actions Available

**List page (`index.tsx`):**
- "New pipeline" button (top-right, and again inside the empty state) toggles the inline `PipelineForm` card (lines 61-64, 117-120).
- Submitting the form calls `createPipeline.mutate(...)`, sending `pipeline_template_id: values.pipeline_template_id || undefined` (line 43) — collapses the empty-string default to `undefined` before POST. On success, closes the form (line 46).
- Each pipeline card has a "View details" link to `/pipeline/{id}` (line 153-158) and a trash-can icon button that calls `deletePipeline.mutate(pipeline.id)` directly, with no confirmation dialog (lines 159-167).

**Detail page (`[id].tsx`):**
- "Back to pipelines" link (top, line 151) and a second "Back to list" link/button at the bottom (line 217) — both just navigate to `/pipeline`.
- No other interactive elements. Stage status, gate `is_passed`, and artifact `is_satisfied` are rendered as read-only badges/icons — there is no button anywhere on this screen to advance a stage's status, approve a gate, or mark an artifact fulfilled. Those state changes can only happen via direct API calls (`PATCH /api/v1/pipelines/stages/{id}`, `PATCH /api/v1/pipelines/gates/{id}`, `PATCH /api/v1/pipelines/required-artifacts/{id}`), which this UI never issues.

## States

**List page:**
- Loading: spinner + "Loading pipelines…" (lines 91-96).
- Error: destructive-bordered card showing `error.message` (lines 98-105).
- Empty (`pipelines.length === 0`): icon + "No pipelines yet" message referencing the "every project must have an active pipeline" rule, with a CTA button (lines 107-123).
- Populated: responsive grid of cards (lines 125-173).
- Create-form submission error: inline destructive text below the form showing `createPipeline.error.message` (lines 82-86). No success toast — success just closes the form and relies on query invalidation to refresh the grid.

**Detail page:**
- Loading: spinner + "Loading pipeline…" (lines 159-164).
- Error: destructive-bordered card showing `error.message` (lines 166-173).
- Not-found: no explicit "pipeline not found" UI state — a 404 from the API falls into the generic `isError` branch above (the `ApiError` thrown by `apiClient` carries `status: 404`, but the component never branches on `error.status`, so the message is just the generic "Request to ... failed with status 404").
- Empty stages (`stages.length === 0`): "No stages defined for this pipeline yet." text inside the Stages card (lines 202-205).
- Populated: responsive grid of `StageCard`s sorted by `order` (lines 207-211).

## Business Rules Surfaced Here

Referencing `docs/BUSINESS_RULES.md` §2 (Pipeline Rules):

- **Rule 1** ("Every project must have an active pipeline") — surfaced only as copy text in the list page's empty state ("Every project must have an active pipeline. Create one to start defining stages.", `index.tsx:114-115`) and in the detail page's Stages card description. Not actually enforced or checked by this screen; the backend doesn't auto-create one either (`backend/app/api/routes/pipeline.py:10-14`).
- **Rule 6** (stages may require mandatory artifacts) and **Rule 7** (a stage cannot complete if mandatory artifacts are missing) — surfaced visually via the "Required artifacts" checklist per stage, with a filled vs. outline `CheckCircle2`/`CircleDashed` icon keyed off `artifact.is_satisfied` (`[id].tsx:86-104`). Not enforced here (read-only) — actual enforcement is `_enforce_stage_advance_rules` in `backend/app/api/routes/pipeline.py:467-522`, reached only via `PATCH /pipelines/stages/{id}`, which this UI never calls.
- **Rule 4/5/8** (stages may require approval/verification; cannot complete if mandatory gates unapproved) — surfaced via the "Requires approval"/"Requires verification" pills (`[id].tsx:65-79`) and the "Gates" checklist keyed off `gate.is_passed` (lines 106-128). Same caveat: display-only, no action to approve a gate from this screen.
- **Rule 9** (blocked stages must prevent dependent stages from advancing) — surfaced only as a dependency *count* ("Depends on N stage(s)", `[id].tsx:130-135`), not which stages, and not their statuses. The blocking logic itself lives entirely server-side (`_BLOCKING_STAGE_STATUSES`/`_TERMINAL_STAGE_STATUSES` checks in `_enforce_stage_advance_rules`).
- **Rule 2** (only one pipeline can be active per project) — not visibly enforced or explained anywhere in this UI. The list/detail pages show an "Active pipeline"/"Inactive" badge (`index.tsx:141`, `[id].tsx:189`) but nothing prevents a user from creating a second `is_active: true` pipeline for the same project through the form (the backend silently deactivates the others — `_deactivate_other_active_pipelines`, `pipeline.py:120-130` — with no surfaced confirmation or warning in the UI).
- **Rule 10** (release approval allowed only when all required gates pass, via `GET /pipelines/{id}/gates-check`) — **not called anywhere in the frontend.** No hook, no page references `gates-check`.
- **Rule 3** (every stage must define order, status, and type) — not user-facing here since this screen has no stage-creation form at all (see Notes); enforced purely by backend schema requirements.

## Dependencies

This screen family depends on the following backend domains/entities (`backend/app/db/models/pipeline.py`, `backend/app/api/routes/pipeline.py`):

- `ProjectPipeline` (primary entity rendered by both list and detail views).
- `PipelineStage` (nested array on `ProjectPipeline`, rendered in detail view).
- `PipelineStageRequiredArtifact` (nested on each stage, rendered as the "Required artifacts" checklist).
- `PipelineStageGate` (nested on each stage, rendered as the "Gates" checklist).
- `PipelineStageDependency` (nested on each stage; only the count is surfaced).
- `Project` — referenced only by raw `project_id` UUID string, no join/display of the project's name (both list and detail show `Project: <uuid>` literally — `index.tsx:145`, `[id].tsx:180`).
- `PipelineTemplate` — referenced only as an optional free-text UUID field in the create form (see below); never fetched, listed, or displayed by name.
- `Artifact` — not directly fetched; only the boolean `is_fulfilled`/`artifact_type` projection via `PipelineStageRequiredArtifact` is shown (and, per the field-mismatch note below, doesn't actually render correctly today).

## Notes / Improvement Opportunities

**PipelineTemplate is not reachable from this UI in any usable way.** `PipelineTemplate` has full backend CRUD (`backend/app/api/routes/pipeline.py:137-260`: create/list/get/update/delete template, plus template-stage and template-required-artifact creation), but:
- There is no `frontend/src/pages/pipeline-template/` or equivalent page, and no hook file analogous to `usePipeline.ts` for templates — confirmed by directory listing and grep across `frontend/src/hooks/` and `frontend/src/pages/`.
- The only template touchpoint in the UI is the "Template ID" free-text input in `PipelineForm.tsx:62-72`, which asks the user to paste a raw UUID with no picker, no validation that the UUID exists, and no preview of what stages/artifacts the template would seed. Since `pipeline_templates` has zero seeded rows in any environment (confirmed in `docs/DATA_MODEL.md` §4), this field is effectively dead in practice today — there is nothing to type in.
- Even if a template UUID were typed in, nothing in `create_pipeline` (`backend/app/api/routes/pipeline.py:268-304`) actually instantiates stages/artifacts *from* the template — the endpoint only stores `template_id` and creates stages from `payload.stages` (which the frontend never populates either, since `PipelineForm` only collects pipeline-level fields, not stages). So "ad hoc creation" is the only path this screen supports in practice: create an empty pipeline, then stages/gates/artifacts would have to be added through some other client (e.g. direct API calls), since no frontend page exists for `POST /pipelines/{id}/stages`, `/stages/{id}/gates`, or `/stages/{id}/required-artifacts` either.

**Field-name mismatches between the Zod schema and the actual backend response (real bug, not cosmetic).** Because `apiClient.get<T>` performs no runtime validation (`frontend/src/lib/api.ts:45-72`) — it's a type-only cast — the field names declared in `frontend/src/hooks/usePipeline.ts`'s Zod schemas silently diverge from what `backend/app/api/schemas/pipeline.py` actually returns, and nothing fails loudly:
- `pipelineCreateSchema` / `projectPipelineSchema` declare `pipeline_template_id` (`usePipeline.ts:94,108`), but the backend's `ProjectPipelineCreate`/`ProjectPipelineOut` field is `template_id` (`backend/app/api/schemas/pipeline.py:215,233`). The create form's POST body key (`PipelineForm.tsx` via `pipelineCreateSchema`) will never actually populate the backend's `template_id` column, and reading it back will always be `undefined` since the response key is `template_id`, not `pipeline_template_id`.
- `pipelineStageSchema` declares `project_pipeline_id` and `order` (`usePipeline.ts:74,77`), but `PipelineStageOut` returns `pipeline_id` and `order_index` (`backend/app/api/schemas/pipeline.py:194,197`). In `[id].tsx:50` the stage number badge falls back to `index + 1` (`stage.order ?? index + 1`), so this mismatch is masked by the fallback rather than surfaced — stages always display in array order, never their true `order_index`, unless the array happens to already be pre-sorted by the backend (it is, via `selectinload`/relationship `order_by="PipelineStage.order_index"` in the model, so the visual bug is currently invisible but the sort in `[id].tsx:145-147`, `(a.order ?? 0) - (b.order ?? 0)`, is dead code that always compares `0 - 0`).
- `stageRequiredArtifactSchema` declares `pipeline_stage_id`, `name`, `is_satisfied` (`usePipeline.ts:53-56`), but `PipelineStageRequiredArtifactOut` returns `stage_id`, `artifact_type` (no `name`), `is_fulfilled` (`backend/app/api/schemas/pipeline.py:119-124`). This means **every required-artifact row in the detail view's checklist (`[id].tsx:90-101`) renders an empty/undefined name and always shows the unsatisfied (`CircleDashed`) icon**, since `artifact.is_satisfied` is always `undefined` (falsy) regardless of the real `is_fulfilled` value.
- `stageGateSchema` declares `pipeline_stage_id`, `requires_approval`/`requires_verification`/`is_passed` (`usePipeline.ts:61-68`), but `PipelineStageGateOut` returns `stage_id`, `gate_type` (one of `approval`/`verification`, not two booleans), and `status` (`pending`/`approved`/`rejected`), not `is_passed` (`backend/app/api/schemas/pipeline.py:148-156`). So **every gate row also always renders as not-passed**, regardless of actual `status`.
- Net effect: the "Required artifacts" and "Gates" checklists in the detail view are effectively decorative today — they will show the artifact/gate count correctly (the array length is real) but every name is blank and every status icon is the "not done" icon, even for artifacts/gates that are actually fulfilled/approved server-side.

**Other observations:**
- No confirmation dialog before deleting a pipeline (`index.tsx:159-167`) — a single click on the trash icon fires the DELETE immediately.
- `useUpdatePipeline` (`usePipeline.ts:158-168`) is exported but has zero call sites in any page — dead code from the screen's perspective (no edit-pipeline UI exists; only create and delete are reachable).
- Detail page has no "not found" branch distinct from the generic error state — a deleted/nonexistent pipeline id just shows the generic "Failed to load pipeline: Request to ... failed with status 404" message.
- Neither list nor detail page resolves `project_id` to a project name — `Project: <uuid>` is shown verbatim, requiring the user to already know which UUID maps to which project (no `useProject`/`useProjects` lookup join present in either file).
- `GET /api/v1/pipelines/{id}/gates-check` (the release-readiness rule 10 helper) has no frontend caller anywhere — there is no "Check release readiness" action on the detail page despite the backend explicitly supporting it.
- The detail page's stage grid has no visual indicator connecting a stage's dependency *count* to which specific stages those are, or their current status — a user cannot tell from this screen alone why a stage shows `blocked` without cross-referencing the API directly.
