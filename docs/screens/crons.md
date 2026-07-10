# Screen: Crons

## Route & Purpose

- Route: `/crons` (registered in `frontend/src/App.tsx:56`, label "Crons" in `frontend/src/components/layout/Sidebar.tsx:72`, icon `Clock`).
- Component: `frontend/src/pages/crons/index.tsx` (`CronsPage`, default export).
- Purpose: a two-tab viewer/editor for the shared `hermes cron` scheduler job store and the Hermes scripts catalog those jobs invoke — lets an operator see every scheduled task across all Hermes profiles (interval, owning agent, status, last/next run), edit or delete a job, browse/copy the script source a job runs, spot broken/unused scripts, and hand off a job or script (plus its file content) to the Workspace chat for help. It is a filesystem-backed operational tool, not one of ForgeHub's own DB-backed domains.

## Components

| File | Role |
|---|---|
| `frontend/src/pages/crons/index.tsx` (`CronsPage`) | Page shell: header, "Sync" button (invalidates both list queries), `Tabs` switching between "Crons" and "Scripts". |
| `frontend/src/pages/crons/index.tsx` (`CronsTab`, local) | Table of cron jobs with view/send-to-chat/edit/delete actions; owns `editingJob`/`viewingJob`/`sendingId` local state. |
| `frontend/src/pages/crons/index.tsx` (`ScriptsTab`, local) | Table of the scripts catalog with view/send-to-chat actions; owns `viewingScript`/`sendingKey` local state. |
| `frontend/src/pages/crons/index.tsx` (`CronEditPanel`, local) | Inline form (name, cron expression, deliver target, enabled checkbox, description/prompt textarea) rendered above the table when a job is being edited. |
| `frontend/src/pages/crons/index.tsx` (`FileViewerOverlay`, local) | Modal overlay that fetches and displays a script's raw file content (read-only `<pre>`), with a "Copy" button. |
| `frontend/src/pages/crons/index.tsx` (`buildCronChatMessage`, `buildScriptChatMessage`, local helpers) | Compose the plain-text draft message handed off to the Workspace chat composer for a job or script. |
| `frontend/src/components/ui/{card,table,badge,button,input,textarea,tabs}.tsx` | shadcn/ui primitives used throughout both tabs. |

## Data & API Calls

| Data shown | Source hook | Backend endpoint | Method |
|---|---|---|---|
| Cron jobs list (all profiles) | `useFoundationCrons()` (`frontend/src/hooks/useFoundationCrons.ts`) | `/api/v1/foundation/crons` | GET |
| Update a cron job (name/description/schedule/deliver/enabled) | `useUpdateCronJob()` | `/api/v1/foundation/crons/{job_id}` | PUT |
| Delete a cron job | `useDeleteCronJob()` | `/api/v1/foundation/crons/{job_id}` | DELETE |
| Scripts catalog (central + per-profile, cross-referenced with jobs) | `useFoundationScripts()` (`frontend/src/hooks/useFoundationScripts.ts`) | `/api/v1/foundation/scripts` | GET |
| Script/job file content (file viewer, send-to-chat) | `useScriptFileContent()` / `fetchScriptContentWithFallback()` | `/api/v1/foundation/scripts/{location}/{name}/content` | GET |

Both list hooks parse the response through a Zod schema (`cronJobListSchema`, `scriptListSchema`) before handing data to the component. "Sync" (`CronsPage.handleSync`) does not refetch directly — it calls `queryClient.invalidateQueries` for `cronJobKeys.list` (`["foundation-crons"]`) and `scriptKeys.list` (`["foundation-scripts"]`), letting TanStack Query refetch.

Backend (`backend/app/api/routes/foundation.py`):
- `list_cron_jobs` / `_list_cron_jobs` reads `jobs.json` under `/hermes-cron` (`_load_raw_jobs`), maps each raw record through `_raw_job_to_out` (derives `status` from `enabled`+`state` via `_job_status`; truncates `description` from the raw `prompt` field to 300 chars via `_truncate_description`), and sorts by `(profile, name)`.
- `update_cron_job` / `_update_cron_job` applies a partial update under the same advisory lock used for delete; validates `schedule_display` as a real cron expression via `croniter` (raises 400 on invalid input) and recomputes `next_run_at`.
- `delete_cron_job` / `_delete_cron_job` removes the job by `id` and atomically rewrites `jobs.json` (`_atomic_write_jobs`: write to a tempfile in the same directory, then `os.replace`), all under the same advisory lock (404 if `id` not found).
- `list_scripts` / `_list_scripts` combines the central catalog (`/hermes-cron`'s real script files) with every profile's own `scripts/` dir, cross-referenced against `jobs_by_script` (jobs keyed by their `script` filename) to derive `referenced_by` and a derived `status` of `ok`/`broken`/`unused`; also synthesizes a `ScriptOut` entry for any job that references a script filename not found in any scanned location, so "missing script" jobs are still visible.
- `get_script_content` / `_resolve_script_read_path` resolves the readable path for a given `(location, name)` — including remapping absolute host-side symlink targets (e.g. `/root/.hermes/cron/x.sh`) to their container-side mount via `_HOST_PATH_REMAPS` — and rejects path-traversal attempts in `name` (400 if it contains `/`, `\`, or is `.`/`..`).

## Actions Available

**Crons tab**
- **Sync** (page-level, applies to both tabs) — invalidate and refetch both lists.
- **View** (eye icon) — open `FileViewerOverlay` showing the job's attached script source; tries the job's own profile scripts dir first, then the central catalog (`fetchScriptContentWithFallback`); disabled if the job has no `script` set.
- **Send to chat** (message-square icon) — builds a text draft (task name, profile, schedule, status, deliver, description, and the script's file content if readable) via `buildCronChatMessage`, stashes it in `useChatHandoffStore.setDraft`, and navigates to `/workspace`.
- **Edit** (pencil icon) — opens `CronEditPanel` inline above the table; fields are name, cron expression (`schedule_display`), deliver target, enabled checkbox, and description/prompt textarea; "Save" calls `useUpdateCronJob`, "Cancel" closes the panel without saving.
- **Delete** (trash icon) — `window.confirm('Delete the cron "{name}" (profile {profile})? This action cannot be undone.')`, then `useDeleteCronJob().mutate(job.id)` on confirm; the button is disabled while a delete is `isPending`.

**Scripts tab**
- **View** (eye icon) — open `FileViewerOverlay` showing the script's own source.
- **Send to chat** (message-square icon) — builds a text draft (name, location, executing agent, path, status, description, file content) via `buildScriptChatMessage`, stashes it, navigates to `/workspace`.
- No edit/delete actions exist for scripts — the Scripts tab is read-only.

**File viewer overlay (both tabs)**
- **Copy** — copies the loaded file content to the clipboard via `navigator.clipboard.writeText`, shows a transient "Copied" state for 1.5s.
- **Close** (X icon, or click outside the modal) — dismisses the overlay.

## States

- **Loading (jobs list)**: centered spinner + "Loading crons…" (`index.tsx:362-367`).
- **Loading (scripts list)**: centered spinner + "Loading scripts…" (`index.tsx:529-534`).
- **Loading (file viewer)**: spinner + "Loading file…" inside the overlay (`index.tsx:175-180`).
- **Empty (no cron jobs)**: card with clock icon, "No crons found" / "No jobs registered in the shared `hermes cron` store." (`index.tsx:378-390`).
- **Empty (no scripts)**: card with scroll icon, "No scripts found" (`index.tsx:545-552`).
- **Error (jobs list failed)**: destructive-bordered card, "Failed to load crons: {error}" (`index.tsx:369-376`).
- **Error (scripts list failed)**: destructive-bordered card, "Failed to load scripts: {error}" (`index.tsx:536-543`).
- **Error (file viewer failed)**: red text inside the overlay, the thrown error's message or "Failed to load file." (`index.tsx:181-183`).
- **Error (edit save failed)**: red text inside `CronEditPanel` showing the mutation error message (`index.tsx:245-247`); the panel stays open so the user can retry.
- **No explicit UI state** for: delete-mutation failure (no error rendered anywhere if `useDeleteCronJob` rejects — see Notes), per-row "sending to chat" failure (the spinner just clears in the `finally` block with no error surfaced).

## Business Rules Surfaced Here

None — filesystem-backed cron/script catalog viewer, outside ForgeHub's core DB domain model (`docs/DATA_MODEL.md` / `docs/BUSINESS_RULES.md` cover Product, Pipeline, Planning, Task, Agent/Skill, Artifact, Governance; this screen's data is not stored in any `company.*` table). The only safety mechanism enforced server-side:

- **Advisory file lock on writes.** Both `update_cron_job` and `delete_cron_job` acquire the same `flock` on `<cron dir>/.jobs.lock` that the live `hermes` CLI and gateway scheduler use (`_cron_jobs_lock`, `backend/app/api/routes/foundation.py:343-352`), so a ForgeHub edit/delete cannot race a concurrent write from the scheduler. Reads (`list_cron_jobs`) do not take the lock.
- **Atomic write.** Both mutating operations rewrite the whole `jobs.json` via a tempfile + `os.replace` (`_atomic_write_jobs`), avoiding a partially-written file if the process is interrupted mid-write.
- **Cron-expression validation.** Editing `schedule_display` is validated with `croniter` server-side before being persisted (400 on invalid expression); there is no equivalent client-side validation in `CronEditPanel` — an invalid expression is only caught after clicking Save.
- **Script-name path-traversal guard.** `get_script_content` rejects any `name` containing `/`, `\`, or equal to `.`/`..` (400).

## Dependencies

- **Host filesystem mount `/root/.hermes/cron` → container `/hermes-cron`** (`docker-compose.yml`, see its cron bind-mount comment) — this is the live, shared job store the `hermes` CLI and gateway scheduler also read/write (`jobs.json`, `.jobs.lock`, `README_crons.md`). Unlike the `governance`/`foundation-agents` mounts in the same compose file, this one is **not** `:ro` — ForgeHub can write to it.
- **Host filesystem mount `/root/.hermes/profiles` → container `/profiles`** — each profile's own `scripts/` directory, scanned for the Scripts tab and used to resolve a job's script-by-profile lookup.
- Both mounts are read directly by `backend/app/api/routes/foundation.py` with no database involved — this router 404s/returns empty data if run outside the container or without equivalent local mounts (per the module's own docstring and `CLAUDE.md`'s note on the `foundation` router).
- **`frontend/src/store/chatHandoff.ts`** (Zustand, not persisted) — the one-shot relay used by "Send to chat" to pre-fill the Workspace page's composer; consumed on mount by `/workspace`.
- **`/workspace` screen** — the navigation target of every "Send to chat" action on this page.

## Notes / Improvement Opportunities

- **Delete has a confirmation step, but it's a native `window.confirm`** (`index.tsx:322`), not a styled in-app dialog consistent with the rest of the shadcn/ui-based UI — functional, but visually inconsistent with the design system mandated by `CLAUDE.md`'s UI governance section.
- **Delete failures are silent.** `useDeleteCronJob` (`frontend/src/hooks/useFoundationCrons.ts:46-54`) has no `onError`, and `CronsTab` never reads `deleteJob.isError`/`deleteJob.error` — if the DELETE request fails (e.g. job already removed concurrently, lock contention, filesystem error), the row simply stays in the table with no feedback to the user beyond the button re-enabling. Contrast with `CronEditPanel`, which does render `updateJob.isError` (`index.tsx:245-247`).
- **No optimistic UI / row-level pending indicator for delete** — the trash button is disabled while *any* delete is pending (`deleteJob.isPending`, `index.tsx:480`), not just the row being deleted; clicking delete on job A briefly disables the delete button for every row, not only A's.
- **Edit form has no client-side cron-expression validation.** `CronEditPanel`'s `schedule_display` input (`index.tsx:261-266`) accepts any string; an invalid expression is only rejected after "Save" is clicked, via the backend's `croniter` check, surfaced as a generic mutation error string.
- **`enabled` vs `status` semantics are slightly indirect.** The edit panel only exposes a single "Enabled" checkbox (`index.tsx:275-286`), derived from `job.status !== "disabled"` — there's no way to distinguish/set a `paused` vs `active` state distinctly from this form even though the backend models three states (`active`/`paused`/`disabled`) and `_update_cron_job` sets `state` to `"scheduled"` or `"paused"` based on the same boolean (`backend/app/api/routes/foundation.py:449-452`). A job already in `state == "paused"` for some other reason and then "enabled" via this checkbox would be reset to `"scheduled"`, not restored to whatever its prior state was.
- **"Sync" button label is misleading.** It only calls `invalidateQueries` (`index.tsx:651-661`) — it does not trigger any actual filesystem/cron-store sync or re-scan beyond what TanStack Query's normal refetch-on-stale would eventually do anyway; it's effectively a manual "refresh."
- **`FileViewerOverlay`'s `useScriptFileContent` query key includes the `candidates` array by reference** (`frontend/src/hooks/useFoundationScripts.ts:90-100`, used at `index.tsx:136`) — a new array literal is constructed on every render of `CronsTab`/`ScriptsTab` (e.g. `index.tsx:350-357`), so TanStack Query's key serialization works only because it deep-serializes the key, but this pattern is fragile and could cause unnecessary cache misses if the array's structure ever changes to include non-serializable values.
- **No pagination/filtering/search** on either table — both the Crons and Scripts tabs render every row returned by their respective endpoint with no client-side search, sort, or server-side paging; could become unwieldy with many profiles/jobs.
- **Description truncation happens server-side and is irreversible in this view.** `_truncate_description` (`backend/app/api/routes/foundation.py:336-340`) caps the job's `prompt` at 300 chars with a trailing "…" before it ever reaches the frontend; the full untruncated prompt is not retrievable from this screen (the edit panel's description textarea is pre-filled with the already-truncated value, so saving an edit without touching the description field would persist the truncated text back into `jobs.json`, silently shortening the original prompt). This looks like a real data-loss risk on the edit path.
