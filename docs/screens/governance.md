# Screen: Governance

## Route & Purpose

Routes: `/governance` (list, `frontend/src/App.tsx:50` — `<Route path="governance" element={<GovernancePage />} />`) and `/governance/:id` (detail, `App.tsx:51` — `<Route path="governance/:id" element={<ApprovalDetailPage />} />`). Both route under the authenticated app layout; "Governance" appears in the sidebar nav (`frontend/src/components/layout/Sidebar.tsx:64`, Gavel icon).

Components: `frontend/src/pages/governance/index.tsx` (list, default export `GovernancePage`) and `frontend/src/pages/governance/[id].tsx` (detail, default export `ApprovalDetailPage`).

Purpose, per the list page's own subtitle (`index.tsx:66-67`): "Approvals for gated transitions -- pipeline stage gates, release readiness, critical skills, and change requests -- backed by audit events and policies." In practice the screen is **Approval-centric only**: it lists/creates/deletes Approval rows and, on the detail page, shows the linked Policy and any AuditEvents whose `entity_type`/`entity_id` point at that approval. There is no Policy list/CRUD UI and no general AuditEvent list/browse UI reachable from this screen (see Notes).

## Components

| File | Role |
|---|---|
| `frontend/src/pages/governance/index.tsx` | List view. Fetches all approvals, renders them in a table, toggles an inline "New approval" form, offers delete-per-row. |
| `frontend/src/pages/governance/[id].tsx` | Detail view for a single Approval. Shows decision metadata, the linked Policy (if any), and a filtered slice of audit events. |
| `frontend/src/pages/governance/ApprovalForm.tsx` | Shared create form (react-hook-form + zod), used inline on the list page only — no edit usage found anywhere in the codebase. |
| `frontend/src/hooks/useGovernance.ts` | TanStack Query hooks + zod schemas for Approval, AuditEvent, Policy. |
| `frontend/src/components/ui/{button,card,badge,table,input,label,textarea,select}.tsx` | shadcn/ui primitives used for layout/status rendering and the form. |

## Data & API Calls

| Data shown | Source hook | Backend endpoint | Method |
|---|---|---|---|
| List of approvals (subject_type, subject_id, status, requested_by, approved_by) | `useApprovals()` (`useGovernance.ts:127-132`) | `RESOURCE` = `/api/v1/governance` (no `/approvals` suffix) | GET |
| Single approval detail | `useApproval(id)` (`useGovernance.ts:134-140`) | `/api/v1/governance/{id}` | GET |
| Governing policy for the approval (`risk_level`, `is_active`, name, description) | `usePolicy(approval?.policy_id)` (`useGovernance.ts:204-210`) | `/api/v1/governance/policies/{id}` | GET |
| Audit events filtered client-side to this approval | `useAuditEvents()` (`useGovernance.ts:178-183`), filtered in `[id].tsx:24-26` | `/api/v1/governance/audit-events` (no entity filter applied — fetches **all** audit events, then filters in JS) | GET |

Mutations triggered from this screen:

| Action | Hook | Backend endpoint | Method |
|---|---|---|---|
| Create approval | `useCreateApproval()` (`useGovernance.ts:142-150`) | `/api/v1/governance` | POST |
| Delete approval | `useDeleteApproval()` (`useGovernance.ts:164-172`) | `/api/v1/governance/{id}` | DELETE |

**Critical mismatch — this screen is wired against API paths and shapes that do not exist on the actual backend (`backend/app/api/routes/governance.py`):**

- The backend router is mounted at `/api/v1/governance` but every concrete route is under a sub-path: `/api/v1/governance/approvals`, `/api/v1/governance/approvals/{id}`, `/api/v1/governance/approvals/{id}/approve`, `/api/v1/governance/approvals/{id}/reject`, `/api/v1/governance/audit-events`, `/api/v1/governance/audit-events/{id}`, `/api/v1/governance/policies`, `/api/v1/governance/policies/{id}` (`governance.py:43,49,84,102,110,117,169,182,200,213,229,244`).
- The frontend's `RESOURCE` constant (`useGovernance.ts:121`) is the bare prefix `/api/v1/governance` with **no `/approvals` segment** — so `useApprovals`, `useApproval`, `useCreateApproval`, and `useDeleteApproval` all call URLs that 404 against the real backend (e.g. `GET /api/v1/governance` instead of `GET /api/v1/governance/approvals`). There is no `PUT /api/v1/governance` either — `useUpdateApproval` (`useGovernance.ts:152-162`) is unused by any page in this family but has the same path bug.
- `useAuditEvents`/`useAuditEvent`/`usePolicies`/`usePolicy` do build correct sub-paths (`${RESOURCE}/audit-events`, `${RESOURCE}/policies`) and would work against the real backend, *if* the approval ever loaded so `policy_id` were available.
- Field-name/shape mismatches between the frontend's zod schemas and the backend Pydantic schemas (`backend/app/api/schemas/governance.py`):
  - Frontend `Approval` uses `subject_type`/`subject_id`/`approved_by`/`decision_notes`; backend `ApprovalOut` uses `entity_type`/`entity_id`/`decided_by`/`comments` (`governance.py` schemas vs `useGovernance.ts:51-64`). No field name is shared except `id`, `status`, `policy_id`, `created_at`, `updated_at`.
  - Frontend `AuditEvent` uses `action`/`metadata`/`occurred_at`; backend `AuditEventOut` uses `event_type`/`payload`/`created_at` (no `occurred_at`).
  - Frontend `Policy` expects `risk_level` and `requires_approval`; the backend `Policy` model/schema has neither field — it has `policy_type` (free-text) and `rules` (JSONB) instead (`db/models/governance.py:48-67`, `api/schemas/governance.py` `PolicyBase`). The detail page's "Governing policy" card (`[id].tsx:132-139`) renders `policy.risk_level`, which would be `undefined` against the real API response.
- Net effect: as wired today, the list page's GET would fail against the real backend (zod parse would also fail even if the URL were fixed, given the field mismatches above), so in practice this screen cannot show the 32 pre-existing `approvals` or 77 pre-existing `audit_events` rows mentioned in `docs/DATA_MODEL.md` §4 without code changes on one side or the other.

## Actions Available

- **New approval** (`index.tsx:70-73`, toggles `showForm`) — reveals an inline `ApprovalForm` card. Submitting calls `createApproval.mutate(...)` (`index.tsx:45-58`), which `POST`s to the (mismatched) approvals endpoint; on success the form collapses (`onSuccess: () => setShowForm(false)`, `index.tsx:55`).
- **Cancel** (inside `ApprovalForm`, `ApprovalForm.tsx:134-138`) — collapses the form without submitting.
- **Delete** (trash icon per row, `index.tsx:179-187`) — calls `deleteApproval.mutate(approval.id)` directly, no confirmation dialog; button disables while `deleteApproval.isPending`.
- **View** (per row, `index.tsx:173-178`) and clicking the subject-type link (`index.tsx:150-155`) — both navigate to `/governance/:id`.
- **Back to governance / Back to list** (`[id].tsx:30-36`, `202-205`) — navigate back to the list.

There is no Approve/Reject action anywhere in the frontend, even though the backend explicitly implements `POST /approvals/{id}/approve` and `POST /approvals/{id}/reject` (`governance.py:110-121`) as the primary decision-making endpoints. The form only lets a user pick an arbitrary `status` value (including directly creating an "approved"/"rejected"/"withdrawn" row, `ApprovalForm.tsx:81-89` against `APPROVAL_STATUSES`) rather than going through the backend's decide-once-and-final flow. There is also no UI to create/edit/deactivate a Policy.

## States

**List page (`index.tsx`):**
- Loading: spinner + "Loading approvals…" while `isLoading` (`index.tsx:99-104`).
- Error: destructive-bordered card with the thrown error's message while `isError` (`index.tsx:106-113`).
- Empty: dedicated empty state (Gavel icon, "No approvals yet" copy, a "New approval" CTA) when the list loads successfully with zero rows (`index.tsx:115-131`).
- Populated: table with Subject / Status / Requested by / Approved by / Actions columns (`index.tsx:133-196`).
- Create-form inline error: if the create mutation fails, an inline destructive message appears under the form (`index.tsx:90-94`).

**Detail page (`[id].tsx`):**
- Loading: spinner + "Loading approval…" while `isLoading` (`[id].tsx:38-43`).
- Error: destructive-bordered card with the thrown error's message while `isError` (`[id].tsx:45-52`).
- No explicit "not found" state distinct from the generic error card (a 404 from the backend would just render as the same error card via `(error as Error)?.message`).
- Policy sub-section degrades gracefully: shows policy details if `usePolicy` resolves, otherwise one of two messages depending on whether `approval.policy_id` is set ("Policy details could not be loaded." vs "No policy is linked to this approval.", `[id].tsx:149-155`) — but does not distinguish a real fetch error from "policy still loading" (no `isLoading`/`isError` destructured from `usePolicy` at all, `[id].tsx:21`).
- Audit trail sub-section: lists matching events, or "No audit events have been recorded for this approval yet." if the filtered list is empty (`[id].tsx:171-198`) — this also covers the case where `useAuditEvents()` itself is still loading or errored, since neither state is checked before rendering (`[id].tsx:22,24`).

## Business Rules Surfaced Here

Cross-referencing `docs/BUSINESS_RULES.md` §7:

- **Rule 1** ("Deciding an Approval writes a companion AuditEvent") is implemented at the backend (`governance.py:148-161`, also on creation at `governance.py:67-79`) but is **not exercised by this screen** — since the UI never calls `/approve` or `/reject`, a user driving this screen alone cannot trigger the audit-write side effect described by the rule; they can only fabricate an already-decided row via direct creation with `status: "approved"`/`"rejected"` in the form, which does *not* go through `_decide_approval` and therefore writes no companion AuditEvent.
- **Rule 2** ("AuditEvent is append-only — no update/delete endpoints") is consistent with what the UI offers: there is no edit or delete control anywhere for audit events on either page — the detail page only ever reads/lists them (`[id].tsx:171-198`). This matches the backend route surface (`governance.py:169-207`, create+list+get only).
- Rule 3 (Project/ProjectPlan/ChangeRequest status CheckConstraints) is not relevant to this screen.
- The backend's "decided approval is final" rule (409 Conflict on re-deciding, `governance.py:134-139`, documented in the route module docstring as implementing SPEC 6.2.10) has **no UI surface at all** on this screen — there's no way to even attempt a re-decision from the frontend since there's no decide action in the first place.

## Dependencies

- **Approval** (`backend/app/db/models/governance.py` `Approval` class) — primary entity for both list and detail.
- **Policy** (`backend/app/db/models/governance.py` `Policy` class) — read-only, linked via `approval.policy_id`, shown only on the detail page.
- **AuditEvent** (`backend/app/db/models/governance.py` `AuditEvent` class) — read-only, shown only on the detail page, filtered client-side to `entity_type === "approval"` matching the current approval's id.
- No dependency on Product/Project/Pipeline/Backlog/Task/Agent/Artifact domains directly from this screen's code, even though Approval's polymorphic `entity_type`/`entity_id` is designed to target rows in several of those domains (e.g. `pipeline_stage_gate`, `release`, `skill`, `change_request`, `artifact` per `APPROVAL_SUBJECT_TYPES`, `useGovernance.ts:24-31`) — the screen never resolves or links to the actual target entity, it just displays the raw `subject_type`/`subject_id` (frontend naming) as text.

## Notes / Improvement Opportunities

- **Policy management is not reachable from this screen at all.** There is no Policy list page, no Policy create/edit form, and no link to one from either Governance page. The only Policy-related UI is the read-only "Governing policy" card on the approval detail page (`[id].tsx:111-157`), which displays a single linked policy and nothing else. Backend full CRUD on `/policies` (`governance.py:213-283`) is entirely unused by the frontend.
- **AuditEvents have no dedicated browse UI.** The only place they're shown is the detail page's filtered "Audit trail" card; there's no `/governance` tab or list to see all 77 pre-existing audit events, search by entity, or page through them. `useAuditEvents()` fetches the entire table unfiltered (no `entity_type`/`entity_id`/`event_type` query params passed, despite the backend supporting all three, `governance.py:182-197`) just to filter client-side for one approval — inefficient and means the detail page implicitly downloads the whole audit log on every visit.
- **The list/detail/create flow is built against API paths that don't exist on the real backend** (see Data & API Calls section above for the full breakdown): `useGovernance.ts:121`'s `RESOURCE` constant omits the `/approvals` segment that every backend approval route requires. This looks like it was written against an earlier or assumed router shape (`/api/v1/governance` exposing approvals directly) that doesn't match the implemented `governance.py`, where approvals/audit-events/policies are each their own sub-resource. As shipped, this screen cannot load, create, or delete approvals against the real API.
- **Field names also don't match** between `useGovernance.ts`'s zod schemas and `api/schemas/governance.py`'s Pydantic schemas (`subject_type`/`subject_id`/`approved_by`/`decision_notes` vs `entity_type`/`entity_id`/`decided_by`/`comments`; `action`/`metadata`/`occurred_at` vs `event_type`/`payload`/(no equivalent); `risk_level`/`requires_approval` vs `policy_type`/`rules`). Even fixing the URL bug above would still leave zod validation failures on every response.
- **No Approve/Reject UI**, despite that being the backend's primary intended interaction for this domain (`governance.py:110-163`, decide-once-and-final). The form instead lets a caller set an arbitrary `status` at creation time (`ApprovalForm.tsx:81-89`), which bypasses the audit-write side effect described in Business Rules §7 Rule 1 and the "decision is final" 409 guard.
- **Delete has no confirmation step** (`index.tsx:179-187`) — a single click removes an approval row immediately, unlike typical destructive-action UX elsewhere that might gate behind a confirm dialog (not verified for other domains in this pass, flagged here only).
- `usePolicy`/`useAuditEvents` results in `[id].tsx` are consumed without checking their own `isLoading`/`isError` (`[id].tsx:21-22`), so a slow or failing policy/audit-events fetch silently renders as "no policy linked" / "no audit events" rather than a distinguishable loading or error state.
- `ApprovalForm.tsx` is exported as a reusable component with `defaultValues`/`submitLabel` props suggesting an edit-mode use case, but no page in the codebase passes those props or uses the form for editing — only the list page's create flow uses it, with all defaults.
