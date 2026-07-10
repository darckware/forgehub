# Screen: Artifacts

## Route & Purpose

- `/artifact` — list view (`frontend/src/pages/artifact/index.tsx`). Shows every `Artifact` row with an inline create form.
- `/artifact/:id` — detail view (`frontend/src/pages/artifact/[id].tsx`). Shows one artifact and its `ArtifactVersion` history.

Both routes are registered in `frontend/src/App.tsx:48-49`. Purpose per the on-screen copy: "Formal deliverables produced by the project — specs, source code, test reports, release notes, and approval records — each tracked across revisions" (`index.tsx:67-68`).

## Components

| File | Role |
|---|---|
| `frontend/src/pages/artifact/index.tsx` | List page: renders the artifact table, the "New artifact" toggle, and the inline create-form card. |
| `frontend/src/pages/artifact/[id].tsx` | Detail page: renders one artifact's metadata (name, description, status badge, type badge), the three linkage cards (project/pipeline stage/task execution), and the read-only version list. |
| `frontend/src/pages/artifact/ArtifactForm.tsx` | Shared `react-hook-form` + Zod form for creating an artifact (also accepts `defaultValues`/`submitLabel` props for reuse, but nothing in the codebase currently calls it for editing — only `index.tsx` uses it, in create mode). |
| `frontend/src/hooks/useArtifact.ts` | TanStack Query hooks (`useArtifacts`, `useArtifact`, `useCreateArtifact`, `useUpdateArtifact`, `useDeleteArtifact`) plus the Zod schemas (`artifactSchema`, `artifactCreateSchema`, `artifactVersionSchema`) and constant arrays `ARTIFACT_TYPES`/`ARTIFACT_STATUSES`. |

## Data & API Calls

| Data shown | Source hook | Backend endpoint | Method |
|---|---|---|---|
| Artifact list (name, type, status, project, version count) | `useArtifacts()` | `/api/v1/artifacts` | GET |
| Single artifact + versions | `useArtifact(id)` | `/api/v1/artifacts/{id}` | GET |
| Create artifact | `useCreateArtifact()` | `/api/v1/artifacts` | POST |
| Update artifact (hook exists, unused by any page) | `useUpdateArtifact(id)` | `/api/v1/artifacts/{id}` | PATCH |
| Delete artifact | `useDeleteArtifact()` | `/api/v1/artifacts/{id}` | DELETE |

No other artifact-related endpoint is called from the frontend. The backend additionally exposes `POST /api/v1/artifacts/{id}/approve` (approve/reject decision body) and the full `ArtifactVersion` sub-resource CRUD (`POST/GET/PATCH/DELETE /api/v1/artifacts/{id}/versions[/{version_id}]`) — none of these have a frontend hook or UI entry point (see Notes).

## Actions Available

- **List view (`index.tsx`):**
  - "New artifact" button toggles the inline create form (`showForm` state, `index.tsx:71-74`).
  - Submitting the form calls `useCreateArtifact().mutate(...)`; on success the form closes (`index.tsx:46-59`).
  - Each row has a "View" link to `/artifact/:id` and a delete (trash icon) button that calls `useDeleteArtifact().mutate(artifact.id)` with no confirmation dialog (`index.tsx:179-187`).
- **Detail view (`[id].tsx`):**
  - "Back to artifacts" link/button (top and bottom) — navigation only, no mutation.
  - No edit, approve, reject, or "add version" actions are present — the detail page is read-only display of whatever `GET /api/v1/artifacts/{id}` returns.
- **Create form (`ArtifactForm.tsx`):**
  - Fields: Name (required), Description, Type (`select`, defaults to `other`), Status (`select`, defaults to `draft`), Project ID (free-text UUID, optional), Pipeline Stage ID (free-text UUID, optional), Task Execution ID (free-text UUID, optional).
  - "Cancel" (only rendered if `onCancel` passed — it is, from the list page) and "Create artifact" submit buttons.

## States

- **Loading:** spinner + "Loading artifacts…" / "Loading artifact…" (`index.tsx:100-105`, `[id].tsx:86-91`), driven by `isLoading` from the respective query hook.
- **Error:** destructive-bordered card showing `Failed to load artifacts: <error.message>` / `Failed to load artifact: <error.message>` (`index.tsx:107-114`, `[id].tsx:93-100`), driven by `isError`/`error`.
- **Empty (list only):** "No artifacts yet" card with a prompt to create one, shown when `artifacts.length === 0` (`index.tsx:116-133`). No analogous empty state is needed on detail (a missing id 404s into the generic error state).
- **Empty versions (detail only):** "No versions recorded for this artifact yet." with a `FileText` icon when `artifact.versions` is empty (`[id].tsx:154-158`).
- **Form submission error:** inline destructive text below the form, `Failed to create artifact: <error.message>` (`index.tsx:91-95`), driven by `createArtifact.isError`.
- **Delete:** no loading/error feedback beyond the button's own `disabled` state while `deleteArtifact.isPending` (`index.tsx:183`) — a failed delete surfaces nothing to the user (see Notes).

## Business Rules Surfaced Here

- **BUSINESS_RULES.md §6 Rule 4** (dangling `pipeline_stage_id`/`task_execution_id` rejected): enforced server-side in `_validate_artifact_links` (`backend/app/api/routes/artifact.py:60-72`), called from both `create_artifact` and `update_artifact`. The frontend **does** surface the resulting error to the user, but only generically — the create form's Project/Pipeline Stage/Task Execution ID fields are plain free-text `Input`s with no existence check, autocomplete, or dropdown (`ArtifactForm.tsx:97-133`); a `400` from a dangling id bubbles up only as `createArtifact.isError` → `Failed to create artifact: Request to /api/v1/artifacts failed with status 400` (`index.tsx:91-95`), via the generic `ApiError` in `frontend/src/lib/api.ts:17-27` — the field-specific `detail` message ("pipeline_stage_id must reference an existing pipeline stage") is not parsed out or attached to the specific field, it's just appended via `Error.message`, which is the generic "Request to ... failed with status 400" string, not the backend's `detail` body. So the user sees a request-failed message, not the specific reason.
- **Approval requires a FINAL version** (rule enforced in `decide_artifact_approval`, `backend/app/api/routes/artifact.py:226-237`): **not surfaced at all** in the frontend — there is no approve/reject UI, so this rule is invisible to users of this screen today. The detail page does display the version list with a "current" badge (`[id].tsx:36-46`), but versions are display-only; there is no way to mark a version FINAL or trigger approval from the UI.
- **Audit event on approve/reject** (BUSINESS_RULES.md §6 Rule 5 / §7): backend writes an `AuditEvent` on approve/reject (`artifact.py:242-250`), but again unreachable from this screen since no approve/reject action exists in the UI.
- **New version reopens governance review** (artifact.py docstring, lines 16-20: creating a version on an `APPROVED` artifact flips it back to `SUBMITTED`): not observable from this screen since there is no "add version" UI.

## Dependencies

- **Artifact** (primary entity, `backend/app/db/models/artifact.py`) — full CRUD surfaced.
- **ArtifactVersion** — read-only, nested under `artifact.versions` in the `GET` response; no independent fetch, create, or edit from this screen.
- **PipelineStage** — referenced by `pipeline_stage_id`; existence-validated server-side on create/update, but the screen has no picker/lookup against the real `pipeline_stages` table, and the detail view shows the raw UUID rather than a resolved stage name (`[id].tsx:135`).
- **TaskExecution** — same pattern as PipelineStage: referenced by `task_execution_id`, existence-validated server-side, raw UUID shown on detail (`[id].tsx:141`), no picker.
- **Project** — `project_id` is accepted by the form and shown on both list and detail, but it is *not* existence-validated anywhere in `artifact.py` (no `_validate_artifact_links`-style check for it) — unlike pipeline_stage_id/task_execution_id, a dangling `project_id` is silently accepted by the backend.

## Notes / Improvement Opportunities

- **Field-name mismatch between frontend schema and backend schema for `ArtifactVersion`.** `frontend/src/hooks/useArtifact.ts:53-62` defines `artifactVersionSchema` with fields `version` (string), `content_url`, `is_current` — none of these exist on the backend's `ArtifactVersionOut` (`backend/app/api/schemas/artifact.py:34-46`), which instead returns `version_number` (int), `location_uri`, and has no `is_current` concept at all. This means:
  - `[id].tsx:43` renders `v{version.version}` — `version.version` will always be `undefined` since the API returns `version_number`, not `version`. Sorting at `[id].tsx:73` (`a.version.localeCompare(b.version, ...)`) will likewise compare `undefined` values.
  - The "current" badge/icon logic (`VersionRow`, `[id].tsx:36-46`) depends on `version.is_current`, a field the backend never sends — it will always default to `false` (per the Zod schema's `.default(false)` at `useArtifact.ts:60`), so **no version will ever show as "current" in the UI**, even though the description text claims "The version marked 'current' is what satisfies pipeline stage requirements" (`[id].tsx:149-151`). The backend model has no `is_current` flag on `ArtifactVersion` at all (`db/models/artifact.py:115-156`) — there is no "current version" concept server-side; this looks like a leftover from an earlier/aspirational design.
  - The "Open" link (`[id].tsx:54-63`) depends on `version.content_url`, which the backend never populates (it sends `location_uri`). This link will never appear.
  - Net effect: the entire Versions section on the detail page is effectively broken against the real backend contract — every version will render as `v` (empty), with no "current" indicator and no working "Open" link. Only `notes` and `checksum` (present under the same name on both sides) actually display correctly.
- **No approve/reject UI for the whole Artifact domain**, despite the backend implementing it fully (`POST /api/v1/artifacts/{id}/approve`, `backend/app/api/routes/artifact.py:203-255`) including the FINAL-version gate and audit logging. This is the single largest functional gap on this screen relative to the backend's capability — there is no way to approve, reject, or even mark a version FINAL from the UI.
- **No "create version" UI.** The backend supports `initial_version` on artifact creation (`ArtifactCreate.initial_version`, `api/schemas/artifact.py:60`) and a full versions sub-resource, but `ArtifactForm.tsx` never collects version data, and there is no "add version" button/form anywhere in `pages/artifact/`.
- **No edit/update UI**, even though `useUpdateArtifact` is fully implemented (`useArtifact.ts:138-148`) and exported — it is simply never imported by either page. An artifact's name/description/type/links cannot be edited from the UI today; the only ways to change an artifact post-creation are delete-and-recreate, or direct API calls.
- **Delete has no confirmation dialog** (`index.tsx:179-187`) — a misclick permanently deletes the artifact and (via `ondelete="CASCADE"` on `artifact_versions.artifact_id`, `db/models/artifact.py:129`) all of its versions, with no undo.
- **Delete failures are silent** — `useDeleteArtifact()` has an `onSuccess` invalidation but no `onError` handler (`useArtifact.ts:150-158`), and `index.tsx` does not read `deleteArtifact.isError`/`error` anywhere, so a failed delete (e.g. a 404 race, or a future FK-constraint failure) gives the user no feedback at all — the row simply stays in place with no explanation.
- **`project_id` is unvalidated.** Unlike `pipeline_stage_id`/`task_execution_id`, nothing in `backend/app/api/routes/artifact.py` checks that a supplied `project_id` references a real `projects` row before saving — it is accepted as a bare string on the model with no FK at all visible in `db/models/artifact.py` (the model docstring only mentions pipeline_stage_id/task_execution_id as the "loose traceability links"; `project_id` does not appear in the model file at all, meaning the `project_id` field accepted by the frontend's Zod schemas (`useArtifact.ts:72`, `88`) and form (`ArtifactForm.tsx:97-107`) has **no corresponding column** in the actual `Artifact` SQLAlchemy model — it is silently dropped server-side since `ArtifactCreate`/`ArtifactUpdate` (`api/schemas/artifact.py:52-69`) also do not declare a `project_id` field. The list/detail pages display `artifact.project_id` from the `GET` response, but since the backend never stores or returns it, it will always render as `—`.
- **Raw UUIDs instead of resolved names.** Both the list (Project column, `index.tsx:165-167`) and detail (`[id].tsx:129-141`) views show raw UUID strings for `project_id`/`pipeline_stage_id`/`task_execution_id` rather than the linked entity's name — there's no cross-fetch to resolve them, making the screen hard to use without separately looking up each id.
- **Status badge variant map omits the backend's actual default state name in one place vs. schema:** the badge maps (`index.tsx:29-38`, `[id].tsx:16-25`) use the key `in_review` for "warning", but the backend's `ArtifactStatus` enum (`db/models/artifact.py:51-60`) uses `submitted`, not `in_review`, as the post-draft state. This means a freshly-submitted artifact's status badge falls through to the `?? "outline"` default instead of showing the intended "warning" styling — a cosmetic but real mismatch between the two status vocabularies (frontend's `ARTIFACT_STATUSES` in `useArtifact.ts:39-45` also says `in_review`, while the backend enum says `submitted`).
