# Screen: Agents

## Route & Purpose

- `/agents` — the org chart (`frontend/src/pages/agent/index.tsx`, component `AgentPage`). Page header carries an agent filter dropdown and the Hermes Foundation sync button; the body is `AgentEcosystemHierarchy`. As of 2026-07-26 there is **no roster table**: once each chart card carried the agent's runtime, profile directory, profile files, Telegram health, skills, sub-agents, crons and scripts, the table below showed strictly less than the card above it. Its two real capabilities — View and Delete (agent and sub-agent) — moved onto the card, and retired agents, which the table used to preserve for audit, got their own chart section.
- `/agents/:id` — detail view (`frontend/src/pages/agent/[id].tsx`, component `AgentDetailPage`). Shows one agent's metadata, an editable description, its registered profile directory, its profile Markdown files, its sub-agents and its granted skills.

Both routes are registered in `frontend/src/App.tsx`. Sidebar entry: "Agents" / `Bot` icon.

**Agent Tools (`/tools`) is reached from this page**, not from the sidebar (2026-07-26) — the tools registry is scoped to the agent roster rather than being a peer destination of it. Its `NAV_SECTIONS` entry carries `hiddenInSidebar: true`, which `Sidebar.tsx` filters out while `CommandPalette` still lists it: dropping the entry outright would have removed it from Cmd/Ctrl+K too, and that is a search surface, not a menu. The tools page carries its own back link to `/agents`.

Purpose: this is the only UI surface for the Agent domain (`agents`, `sub_agents`, `skills`, `agent_skills`, `sub_agent_skills`, `agent_cost_rates`, `agent_capacities`) — it lets a user inspect the roster of executor/coordinator agents available for `TaskAssignment`, see what sub-agents and governed skills each one carries, and pull a fresh roster from the Hermes Foundation filesystem source of truth.

## Components

| File | Role |
|---|---|
| `frontend/src/pages/agent/index.tsx` | Page shell: title, agent filter dropdown, "Sync from Foundation" action, sync result/error banners, and the chart. |
| `frontend/src/pages/agent/[id].tsx` | Detail view: agent header (name/mission/status/type/runtime/layer/tier), editable description card, editable **profile directory** card, sub-agents table, skills table with remove action, embeds `AgentProfileFilesCard`. |
| `frontend/src/pages/agent/AgentProfileFilesCard.tsx` | **One tab per profile file**, each with a rendered read view and an editor. Covers the full set — `SOUL.md`, `IDENTITY.md`, `USER.md`, `TOOLS.md`, `AGENTS.md`, `FOUNDATION_LINK.md`, `HEARTBEAT.md`, `MEMORY.md`, `CONTINUITY.md`, the runtime extra (`CLAUDE.md`) and the optional `<PROFILE>_SUBAGENTS.md` — with a one-line explanation of what each file is for. The tab strip scrolls horizontally (up to 11 tabs); a dot on a tab marks a file that does not exist yet. Rendered for **every** agent, not only Hermes profiles. |
| `frontend/src/components/TelegramStatusBadge.tsx` | Telegram channel health icon, shown in the org chart, the list table and the detail header. |
| `frontend/src/components/AgentProfileFileChips.tsx` | One chip per profile file, on the org chart card's profile-directory line. The chip list is computed client-side (`profileFileNamesFor`, mirroring the backend allow-list) so a dozen cards cost zero requests; opening a chip fetches just that file and previews it as rendered Markdown. |
| `frontend/src/pages/agent/AgentAutomationCard.tsx` | Detail-page card: the agent's `hermes cron` jobs and its profile `scripts/` directory, both keyed off `profile_slug`. Surfaces a corrupted `jobs.json` as an explicit error — that state stops the profile's scheduler entirely. |
| `frontend/src/components/AgentEcosystemHierarchy.tsx` | Org chart. Splits the roster by runtime family (Hermes system agents vs external CLI runtimes), then by layer/tier/department inside the Hermes side. Skills and sub-agents are behind per-agent collapses with their own vertical scrollbars. |
| `frontend/src/hooks/useAgent.ts` | Zod schemas + TanStack Query hooks for `Agent`/`SubAgent`/`Skill`/`AgentSkill`/`SubAgentSkill`/`AgentCostRate`/`AgentCapacity` and the Hermes sync mutation. |
| `backend/app/core/agent_profile_files.py` | Resolves an agent's profile directory (registered `home_path`, else the runtime convention), the per-agent filename allow-list, and the host↔container path translation. |

## Data & API Calls

| Data shown | Source hook | Backend endpoint | Method |
|---|---|---|---|
| Agent list (with nested `sub_agents`) | `useAgents()` | `/api/v1/agents` | GET |
| Single agent detail (with `sub_agents`, `agent_skills`, `cost_rates`, `capacities`) | `useAgent(id)` | `/api/v1/agents/{id}` | GET |
| Skill catalog (to resolve `agent_skills[].skill_id` → name/version/origin/risk/approval) | `useSkills()` | `/api/v1/agents/skills` | GET |
| Hermes Foundation sync (agents/sub-agents/skills/grants upserted) | `useSyncHermesAgents()` | `/api/v1/agents/sync/hermes-foundation` | POST |
| Description edit | `useUpdateAgent(id)` | `/api/v1/agents/{id}` | PATCH |
| Skill removal (revoke grant) | `useRemoveSkillFromAgent(id)` | `/api/v1/agents/{id}/skills/{agentSkillId}` | DELETE |
| Profile file inventory (which files exist, size, mtime) | `useAgentProfileFiles(id)` | `/api/v1/agents/{id}/profile-files` | GET |
| Profile Markdown file content | `useAgentProfileFile(id, filename)` | `/api/v1/agents/{id}/profile-files/{filename}` | GET |
| Profile Markdown file save | `useUpdateAgentProfileFile(id, filename)` | `/api/v1/agents/{id}/profile-files/{filename}` | PUT |
| Profile directory registration | `useUpdateAgent(id)` | `/api/v1/agents/{id}` (`home_path`) | PATCH |
| Telegram channel status (whole roster, polled every 60s) | `useAgentsTelegramStatus()` | `/api/v1/agents/telegram-status` | GET |
| Cron jobs per profile | `useFoundationCrons()` | `/api/v1/foundation/crons` | GET |
| Profile scripts per profile | `useFoundationAllScripts()` | `/api/v1/foundation/scripts` | GET |

Hooks defined in `useAgent.ts` but **not called anywhere in these two page files** (verified by grep across `frontend/src/pages/agent/`): `useCreateAgent`, `useDeleteAgent`, `useCreateSubAgent`, `useDeleteSubAgent`, `useAssignSkillToAgent`. See Notes.

## Actions Available

- **Sync from Hermes Foundation** (`index.tsx:63-74`) — button in the list view header, calls `POST /api/v1/agents/sync/hermes-foundation`. This is the only sync trigger found in the codebase; it upserts the `Hermes` coordinator agent, the agent roster (matched by `profile_slug`), sub-agent WORKER/ROLE catalogs, skills (deduped by name+version), and `agent_skills` grants (created with `inheritable=True`) — all from Hermes Foundation's on-disk canonical docs (`backend/app/core/hermes_sync.py`), never from request input. Re-running is safe/idempotent per the route docstring (`backend/app/api/routes/agent.py:169-178`): only Hermes-mirrored fields (`layer`, `runtime_tier`, `telegram_required`, `has_profile`, `mission`, `source_path`) are refreshed on existing agents; manually edited fields (`name`, `status`, `is_active`, `agent_type`, `description`) are left untouched after first creation.
- **View agent** (`index.tsx:213-218`, also per sub-agent row "View parent") — navigates to `/agents/:id`.
- **Edit description** (`[id].tsx:143-176`) — inline textarea + Save/Cancel, calls `PATCH /api/v1/agents/{id}` with `{ description }` only.
- **Remove skill grant** (`[id].tsx:284-293`) — trash icon per skill row, calls `DELETE /api/v1/agents/{id}/skills/{agentSkillId}` (revokes the `agent_skills` association row, not the `Skill` itself).
- **View / edit a profile Markdown file** (`AgentProfileFilesCard.tsx`) — pick the file's tab; it opens in a rendered Markdown read view, and the View/Edit toggle switches to a textarea. Save calls `PUT /api/v1/agents/{id}/profile-files/{filename}`, only enabled while the buffer differs from the loaded content (`isDirty`). Saving a file that does not exist yet creates it.
- **Register profile directory** (`[id].tsx`) — inline path field, calls `PATCH /api/v1/agents/{id}` with `{ home_path }`. Empty clears the override and restores the runtime default.
- **Filter by agent** (`index.tsx`) — dropdown left of the sync button. Selecting one puts the chart in focused mode: that agent's card alone, with the ecosystem counters and the baseline warning hidden (they are statements about the whole ecosystem and would be lies about a single card). Built from the full roster so a retired agent can still be selected.
- **Edit an agent** (`AgentEcosystemHierarchy.tsx`) — pencil icon in the card footer, navigates to `/agents/:id`. The agent name in the card header is a link to the same place.
- **Delete an agent or sub-agent** (`AgentEcosystemHierarchy.tsx`) — trash icon in the card footer, and per row inside the Sub-agents collapse. Same `ConfirmDialog` the removed table used.
- **Open Agent Tools** (`index.tsx`) — button right of Sync.
- **Preview a profile file from the org chart** (`AgentProfileFileChips.tsx`) — click a file chip on an agent card's directory line; it fetches that one file and renders it inline (scrollable, read-only). Editing stays on the agent page.
- **Inspect an agent's crons and scripts** — collapsed sections on the org chart card, and a full table pair on the detail page.

Not present on either screen, despite backend + hook support: create agent, delete agent, create/delete sub-agent, grant a skill to an agent (only revoke), any skill catalog management (create/approve/review a `Skill`), cost rate or capacity display/management.

## States

- **List loading**: spinner + "Loading agents…" (`index.tsx:124-129`), driven by `useAgents().isLoading`.
- **List error**: destructive-bordered card with the thrown error's message (`index.tsx:131-138`).
- **List empty**: "No agents yet" + hint to use the sync button (`index.tsx:140-152`), shown only when the agents array is loaded and has length 0.
- **Sync pending**: spinner replaces the icon on the sync button, button disabled (`index.tsx:66-72`).
- **Sync error**: destructive card showing `syncHermes.error.message` (`index.tsx:77-84`).
- **Sync success**: result card with created/updated counts for agents/sub-agents/skills/skill grants, plus any `warnings[]` returned by the backend rendered in destructive text (`index.tsx:86-121`).
- **Detail loading**: spinner + "Loading agent…" (`[id].tsx:85-90`).
- **Detail error**: destructive card with error message (`[id].tsx:92-98`).
- **Detail not found**: no explicit "agent not found" state — if `agent` is undefined and not loading/erroring, the page just renders nothing below the back-link (this only matters if the API ever returns a 200 with an empty body, since a 404 is caught by `isError`).
- **Description edit error**: inline destructive text under the textarea (`[id].tsx:159-163`).
- **Sub-agents empty**: italic "No sub-agents yet." (`[id].tsx:226-228`).
- **Skills empty**: italic "No skills associated with this agent yet." (`[id].tsx:301-305`).
- **Profile file loading/error**: per-tab spinner / destructive text (`ProfileFilesCard.tsx:44-59`).
- **Profile file save**: error text, or "Saved." confirmation once dirty state clears (`ProfileFilesCard.tsx:75-92`).

## Business Rules Surfaced Here

Citing `docs/reference/BUSINESS_RULES.md` §5 (Skill Rules):

- **§5 rules 1-4** (skill must have version, origin, risk level, permissions) — surfaced read-only in the detail view's skills table: version is appended to the skill name (`[id].tsx:263-267`), origin and risk level each get their own column with a badge (`[id].tsx:269-279`, risk badge colored via `RISK_VARIANT`), but **permissions** (the `Text` field declared required at the DB layer) is not displayed anywhere on this screen.
- **§5 rule 5** (critical skills require approval) — the skills table shows an "Approval" column rendering "Approved"/"Not approved" from `skill.is_approved` (`[id].tsx:281-283`), but the screen has no action to grant approval (no approve button, no risk-level-aware gating in the UI) — the backend enforces the actual gate (critical skills can't self-approve at creation; `agent.py:332-347`) but no part of this screen exercises it.
- **§5 rule 6** (third-party skills require security review before approval) — not surfaced at all in either page; `security_reviewed` is part of the `Skill` schema (`useAgent.ts:47`) but never rendered.
- **§5 rule 7** (sub-agents may only use skills explicit or inherited from the parent, scoped via `permission_scope`) — the sub-agent table on the detail page shows name/description/status only (`[id].tsx:201-225`); it does **not** display `permission_scope` or the sub-agent's own skill grants, so this rule's effect is invisible on screen even though it's enforced server-side (`_assert_skill_grantable_to_sub_agent`, `agent.py:607-630`).
- **§5 rule 8** (approved skills are immutable, new version required for changes) — not surfaced; no skill-editing UI exists on this screen at all (consistent with there being no skill-management UI here).

No Pipeline/Task/Project rules are surfaced on this screen — it is Agent-domain only.

## Dependencies

- **Agent** — primary entity, full list/detail data.
- **SubAgent** — nested under Agent (`sub_agents[]`), rendered on both list (flattened) and detail.
- **Skill** — top-level catalog (`/api/v1/agents/skills`), joined client-side via `skillById` map (`[id].tsx:73`) to resolve names/versions/origin/risk/approval for each `AgentSkill` row.
- **AgentSkill** — association table; the detail page's "Skills" table iterates `agent.agent_skills[]` and removal targets this row's id.
- **SubAgentSkill** — modeled and has full hook/route support, but **not used anywhere on this screen** (no sub-agent skill grants are displayed or managed here).
- **AgentCostRate**, **AgentCapacity** — modeled (`agent.cost_rates`, `agent.capacities` are part of `AgentDetailOut`/`agentSchema`) but **not rendered anywhere on this screen** despite the task prompt's expectation that the detail view shows "cost rates, capacity" — see Notes.

## Notes / Improvement Opportunities

- **Cost rates and capacity are fetched but never rendered.** `agentSchema` includes `cost_rates`/`capacities` (`frontend/src/hooks/useAgent.ts:129-130`) and `AgentDetailOut` eager-loads them server-side (`backend/app/api/routes/agent.py:95-96`), but `[id].tsx` never reads `agent.cost_rates` or `agent.capacities` — no card/section displays them, and there are no hooks/UI to create them either (`POST /{agent_id}/cost-rates` and `POST|GET|PATCH /{agent_id}/capacity` exist on the backend with no frontend caller at all, not even in `useAgent.ts`). This is a backend-ahead-of-frontend gap.
- **No create/delete UI for Agent or SubAgent.** `useCreateAgent`, `useDeleteAgent`, `useCreateSubAgent`, `useDeleteSubAgent` are all defined in `useAgent.ts` (lines 190-220, 244-266) but never invoked from `index.tsx` or `[id].tsx`. The only way to populate agents/sub-agents today is the Hermes sync; manual registration of an agent or sub-agent (which the SPEC's domain model clearly supports) has no UI path.
- **No skill-grant UI, only revoke.** `useAssignSkillToAgent` exists (`useAgent.ts:283-292`) but is not called; a user can remove a skill grant from the detail page (trash icon) but cannot add one back through the UI — the only way skills get attached to agents is via the Hermes sync (which always grants `inheritable=True`).
- **No skill catalog management UI.** Skill create/update/delete (`POST/PATCH/DELETE /api/v1/agents/skills...`) and the approval/security-review workflow are fully implemented on the backend (`agent.py:332-419`) but there is no `frontend/src/pages/skill/` (or similar) screen at all — skills can currently only be viewed indirectly, joined into an agent's detail page.
- **`permission_scope` invisible.** `SubAgent.permission_scope` is part of the Zod schema (`useAgent.ts:81`) and the DB model, but the sub-agents table on the detail page (`[id].tsx:202-209`) only renders name/description/status — the field that actually encodes the SPEC §5 rule 7 boundary is never shown to the user.
- **No "not found" / 404 empty state on the detail page.** If `agent` resolves to `undefined` without `isLoading`/`isError` being true (e.g., a malformed response), the page silently renders just the back-link with no body and no error message (`[id].tsx:101` guard simply skips rendering).
- **Profile files are per-agent, not per-Hermes-profile (2026-07-26).** The card used to be gated on `agent.profile_slug` and read through `/api/v1/foundation/profiles/{slug}/files/...`, which walks the `/profiles` mount — so the four external CLI runtimes (Porthus/claude, Aramis/codex, Dartan/agy, Vector/openclaw) could never show their own identity files, and only six of the ten canonical files were reachable at all. Resolution now goes through the agent's own `home_path`/runtime, and the older foundation route is left in place untouched for its existing callers.
- **List view "Layer / Tier" and "Sub-agents count" columns are blank (`—`) for sub-agent rows** (`index.tsx:244-245`) since those columns are agent-only; acceptable given the flattened-table design but slightly redundant given sub-agents already render under their parent.
- **Sync result banner persists across re-syncs** via `syncHermes.isSuccess`/`isError` mutation state — there's no explicit "dismiss" control, so the banner only changes when another sync is triggered or the page is reloaded.

## Telegram channel status

The ecosystem's human channel is Telegram, one bot per Hermes profile. The badge folds **two independent signals** (`backend/app/core/agent_telegram.py`), deliberately kept apart because they fail apart:

- **installed** — `TELEGRAM_BOT_TOKEN` *and* `TELEGRAM_HOME_CHANNEL` present in the agent's own profile `.env`, read off the resolved profile directory. The token never leaves the backend: it is reduced to a boolean before the response is built (only the home-channel *name* is returned).
- **running** — the systemd unit `hermes-gateway-<profile>.service` is active. That daemon is what long-polls Telegram, so *installed but not running* means messages silently go nowhere; it gets its own state (`not_running`), not a generic error. The backend container has no systemd, so this goes through the host-bridge `/v1/exec`, one call for the whole roster.

States: `ok` (green) · `not_running` (red) · `not_configured` (amber) · `unknown` (muted) · `not_applicable` (faint). `running` is `null` — and the status degrades to `unknown`, never to red — when the host-bridge could not be reached: *we failed to observe* must not render as *we observed a failure*.

Only Hermes profiles have a gateway unit. The four external CLI runtimes carry a `profile_slug` too (it is their Inbox addressing key, not a directory under `/root/.hermes/profiles`), so the unit name is keyed off `runtime_type == "hermes"` as well — keying off the slug alone invented a `hermes-gateway-porthus.service` and reported that non-existent unit as down.

## Crons and scripts per agent

`hermes cron` job stores and script directories are **per profile** on disk (`<profile>/cron/jobs.json`, `<profile>/scripts/`), so both are keyed off `profile_slug` — an agent with no Hermes profile owns neither, and that is stated rather than shown as an empty table.

Two things worth knowing when touching this:

- A cron job's `status` only mirrors the enabled/paused flag; **`health` is what says whether it actually runs** (`ok` / `error` / `overdue` / `never_ran` / `off`, computed by `foundation.py`'s `_job_health`). `overdue` means `next_run_at` is in the past — the scheduler is not ticking it. The badge colours off `health`, never `status`.
- `cronData.store_errors` must never be swallowed: a `jobs.json` that fails to parse does not merely hide that profile's jobs, it makes that profile's gateway refuse to tick at all, so every cron in the profile has stopped. `AgentAutomationCard` renders it as a destructive banner.

Scripts come from `/api/v1/foundation/scripts` (full per-profile catalog off the filesystem), **not** `/api/v1/scripts` (DB-backed, deliberately only the scripts a cron job references). Note the two endpoints' `referenced_by` shapes differ — the Foundation one carries no `last_run_at` — which is why `useFoundationScripts.ts` defines a separate ref schema instead of reusing `cronJobRefSchema`.
