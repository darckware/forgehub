# Screen: Backlog

## Route & Purpose

- `/backlog` — list view of all `PlanningItem` rows (the backlog), with an inline create form.
- `/backlog/:id` — detail view of a single `PlanningItem`, showing its `FeatureRequest`/`BugReport` specialization, version scope, and triage history.

Purpose: capture and triage planning items (features, bugs, hotfixes, improvements, technical debt, refactoring, security fixes, research, documentation) before they are scoped into a product version and, eventually, broken into tasks.

## Components

| File | Role |
|---|---|
| `frontend/src/pages/backlog/index.tsx` | List page: table of planning items, inline "Create planning item" card, delete action. |
| `frontend/src/pages/backlog/[id].tsx` | Detail page: planning item header, feature/bug specialization card, version scope card, triage decisions card. |
| `frontend/src/pages/backlog/PlanningItemForm.tsx` | Shared create form (react-hook-form + Zod) for title/description/type/status/priority/product_version_id/project_id, plus a conditional bug-details sub-section (severity/environment/detected_in_version) when `item_type` is `bug` or `hotfix`. |
| `frontend/src/hooks/useBacklog.ts` | TanStack Query hooks and Zod schemas for `PlanningItem` (and nested `FeatureRequest`/`BugReport`/`VersionScopeItem`/`TriageDecision` read shapes). |
| `backend/app/api/routes/backlog.py` | FastAPI routes for `planning-items`, `feature-requests`, `bug-reports`, `version-scope-items`, `triage-decisions`. |

Note: the detail page (`[id].tsx`) has no edit form — `useUpdatePlanningItem` exists in the hook file but is not called from any component in this screen family. There is also no UI here for creating a `FeatureRequest`/`BugReport` intake row directly or for the `convert` flow, or for creating a `VersionScopeItem`/`TriageDecision` — those backend endpoints exist but are not wired to this screen (read-only display only).

## Data & API Calls

| Data shown | Source hook | Backend endpoint | Method |
|---|---|---|---|
| List of planning items (title, type, status, priority, version scope count) | `usePlanningItems()` | `/api/v1/planning-items` | GET |
| Create planning item | `useCreatePlanningItem()` | `/api/v1/planning-items` | POST |
| Delete planning item | `useDeletePlanningItem()` | `/api/v1/planning-items/{id}` | DELETE |
| Single planning item detail (incl. nested `feature_request`, `bug_report`, `version_scope_items`, `triage_decisions`) | `usePlanningItem(id)` | `/api/v1/planning-items/{id}` | GET |

`useUpdatePlanningItem(id)` (PUT `/api/v1/planning-items/{id}`) is defined in `useBacklog.ts` but unused by any component in this screen family.

## Actions Available

- **New planning item** (list page): toggles the inline `PlanningItemForm` card; on submit, calls `useCreatePlanningItem`, closing the form on success. Empty optional fields (`description`, `product_version_id`, `project_id`, `severity`, `environment`, `detected_in_version`) are converted to `undefined` before the POST body is built (`frontend/src/pages/backlog/index.tsx:62-68`).
- **Delete** (list page, per row): calls `useDeletePlanningItem(item.id)`, disabled while a delete is pending. No confirmation dialog.
- **View** (list page, per row): navigates to `/backlog/:id`.
- **Back to backlog / Back to list** (detail page): links back to `/backlog`.

No triage, conversion (feature/bug request → planning item), or version-scoping actions are exposed from this screen — they are read-only displays of data presumably created elsewhere (or only via direct API calls), even though the backend fully supports those operations.

## States

- **Loading**: both list and detail show a centered spinner (`Loader2`) with text ("Loading planning items…" / "Loading planning item…").
- **Empty** (list only): when `planningItems` is an empty array, shows a `ClipboardList` icon, "No planning items yet" message, and a "New planning item" button. No empty-state messaging exists in the detail view (not applicable — a missing ID would instead surface as an error or loading-forever state, see Notes).
- **Error**: both list and detail show a destructive-bordered card with `AlertCircle` and the error message (`(error as Error)?.message`). The create-form section also shows its own inline error message when `createPlanningItem.isError`.
- Within detail page: if `feature_request`/`bug_report` are both absent, a fallback "Details" card states the item type "carries no nested specialization in this view." If `version_scope_items`/`triage_decisions` are empty, each card shows a placeholder sentence instead of being hidden.

## Business Rules Surfaced Here

- **Rule (Traceability §6.1, BUSINESS_RULES.md): "A `PlanningItem` must reference an existing `Project`."** Enforced server-side in `create_planning_item` (`backend/app/api/routes/backlog.py:87-91`, 400 if `project_id` doesn't resolve to a real `Project`) and in `update_planning_item` (project_id cannot be cleared, lines 148-158). **Not surfaced in the UI** — see Notes below; the form does not guarantee a valid `project_id` is sent.
- **Baselined items are immutable (Planning Rules §3.2 / Traceability convention).** `update_planning_item` and `delete_planning_item` both reject the call with 409 if `item.baselined` is true (`backend/app/api/routes/backlog.py:132-140`, `172-176`). The detail page does display a `baselined` boolean implicitly via `PlanningItemOut`, but **no badge or indicator for `baselined` is rendered anywhere in `[id].tsx` or `index.tsx`** — a user has no visual cue that an item is locked.
- **Scoping requires triage first.** `create_version_scope_item` rejects scoping a planning item still in `status == "new"` (`backend/app/api/routes/backlog.py:380-385`, 409). The detail page displays existing `version_scope_items` (read-only) but has no UI to create one, so this rule cannot currently be triggered or violated from this screen.
- **Triage decision drives status transitions.** Recording a `TriageDecision` with `outcome="accepted"` advances `PlanningItem.status` to `triaged`; `"rejected"` moves it to `rejected` (`backend/app/api/routes/backlog.py:456-461`). The detail page displays the resulting `triage_decisions` list (decision, rationale, decided_by, decided_at) but has no UI to record a new decision.

## Dependencies

- **Project** — required FK on every `PlanningItem` (existence-checked server-side); the screen reads/writes a raw `project_id` string but never fetches or validates against the `Project` domain client-side.
- **ProductVersion** — optional FK (`product_version_id` at creation / `target_version_id` once scoped); also referenced indirectly via `VersionScopeItem.product_version_id`, shown in the detail page only as a raw UUID string (`item.version_scope_items[].product_version_id`, no name/version lookup).
- **PlanningItem** — the primary entity this screen manages.
- **FeatureRequest** / **BugReport** — 1:1 specializations, displayed when present on the fetched `PlanningItem`, but this screen has no path to create one directly (only the unified `PlanningItemForm`, which posts a single `PlanningItem`, not a `FeatureRequest`/`BugReport` intake row).
- **VersionScopeItem** — displayed read-only in the detail page's "Version scope" card.
- **TriageDecision** — displayed read-only in the detail page's "Triage decisions" card.

## Notes / Improvement Opportunities

**P1 — Form will fail to submit without a valid project: `project_id` is a free-text input, not a project picker, and is optional client-side while required server-side.**

- `frontend/src/pages/backlog/PlanningItemForm.tsx:133-139` renders `project_id` as a plain `<Input>` with placeholder "uuid of linked project" — there is no `<Select>`/combobox backed by a Project list (no `useProjects()` call exists anywhere in this file or its imports).
- `frontend/src/hooks/useBacklog.ts:127` defines `project_id: z.string().optional().or(z.literal(""))` in `planningItemCreateSchema` — the Zod resolver will happily validate and submit an empty string.
- `frontend/src/pages/backlog/index.tsx:64` explicitly rewrites an empty `project_id` to `undefined` before calling `createPlanningItem.mutate(...)`, i.e. the payload sent to the backend can have no `project_id` key at all if the user leaves the field blank (which is the field's default value, `PlanningItemForm.tsx:47`).
- The backend schema `PlanningItemBase.project_id: uuid.UUID` (`backend/app/api/schemas/backlog.py:31`) has no default and is not `Optional` — FastAPI/Pydantic will reject a request missing `project_id` with `422 Unprocessable Entity` before the route body (the explicit 400 check at `backend/app/api/routes/backlog.py:87-91`) ever runs.
- **Net effect: any user who submits the "New planning item" form without manually typing a project UUID into a bare text box gets a hard validation failure**, surfaced only as a generic `createPlanningItem.isError` message ("Failed to create planning item: Request to /api/v1/planning-items failed with status 422") — no field-level guidance, since the Zod-side validation never caught it. Even when a UUID is typed, there is no way for the user to know which project UUIDs are valid without leaving this screen (no autocomplete, no project list reference, no link to `/projects`).
- Fix would need: (a) a real project picker (dropdown/combobox sourced from a `useProjects()`-style hook, analogous to other domain forms) wired into `PlanningItemForm`, and (b) tightening `planningItemCreateSchema.project_id` to a required, validated field so the Zod resolver itself blocks submission with a visible inline error instead of deferring to a 422 round-trip.

**Other findings:**

- The detail page (`[id].tsx`) has no edit affordance at all — `useUpdatePlanningItem` is defined in the hooks file but dead code from this screen's perspective. There is no way to change status, priority, or any other field of an existing planning item through the UI.
- No `baselined` indicator is rendered anywhere, even though it gates mutability (see Business Rules above) — a user attempting to delete or (if editing existed) edit a baselined item would only discover the 409 after the fact, via a generic error toast/message at best.
- The `product_version_id` field in the create form is also a bare UUID text input with no picker, same class of issue as `project_id` but lower severity since it is optional both client- and server-side.
- The delete action on the list page has no confirmation step — a misclick immediately fires `DELETE /api/v1/planning-items/{id}`.
- This screen has no entry points for the `FeatureRequest`/`BugReport` intake-and-convert flow described in the backend route docstring (SPEC 8.1/8.2) — `convert_feature_request`/`convert_bug_report` exist server-side but nothing in `frontend/src/pages/backlog/` calls them; the only creation path is the unified `PlanningItemForm`, which always creates a `PlanningItem` directly (with a conditional bug-detail sub-form) and never a standalone `FeatureRequest`/`BugReport` row.
- Status badges on the list (`STATUS_VARIANT` map in `index.tsx:39-50`) do not include a mapping for `"rejected"`'s sibling state used elsewhere — actually `rejected` is present, but note the map has no entry for any future/unlisted status; those fall back to `"outline"` variant safely.
