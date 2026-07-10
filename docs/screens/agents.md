# Screen: Agents

## Route & Purpose

- `/agents` — list view (`frontend/src/pages/agent/index.tsx`, component `AgentPage`). Shows every registered `Agent` with its `sub_agents` flattened underneath as indented rows, plus a button to trigger the Hermes Foundation sync.
- `/agents/:id` — detail view (`frontend/src/pages/agent/[id].tsx`, component `AgentDetailPage`). Shows one agent's metadata, an editable description, its sub-agents, its granted skills, and (if the agent has a Hermes profile) its profile Markdown files.

Both routes are registered in `frontend/src/App.tsx:46-47`. Sidebar entry: "Agents" / `Bot` icon, `frontend/src/components/layout/Sidebar.tsx:67`.

Purpose: this is the only UI surface for the Agent domain (`agents`, `sub_agents`, `skills`, `agent_skills`, `sub_agent_skills`, `agent_cost_rates`, `agent_capacities`) — it lets a user inspect the roster of executor/coordinator agents available for `TaskAssignment`, see what sub-agents and governed skills each one carries, and pull a fresh roster from the Hermes Foundation filesystem source of truth.

## Components

| File | Role |
|---|---|
| `frontend/src/pages/agent/index.tsx` | List view: table of agents + nested sub-agent rows, "Sync from Hermes Foundation" action, sync result/error banners. |
| `frontend/src/pages/agent/[id].tsx` | Detail view: agent header (name/mission/status/type/layer/tier), editable description card, sub-agents table, skills table with remove action, embeds `ProfileFilesCard`. |
| `frontend/src/pages/agent/ProfileFilesCard.tsx` | Tabbed editor (`SOUL.md`/`MEMORY.md`/`TOOLS.md`/`AGENTS.md`/`HEARTBEAT.md`/`USER.md`) for the agent's Hermes profile Markdown files on disk; only rendered when `agent.profile_slug` is set. |
| `frontend/src/hooks/useAgent.ts` | Zod schemas + TanStack Query hooks for `Agent`/`SubAgent`/`Skill`/`AgentSkill`/`SubAgentSkill`/`AgentCostRate`/`AgentCapacity` and the Hermes sync mutation. |
| `frontend/src/hooks/useFoundation.ts` | Hooks for reading/writing the raw profile Markdown files (`/api/v1/foundation/profiles/...`), used only by `ProfileFilesCard`. |

## Data & API Calls

| Data shown | Source hook | Backend endpoint | Method |
|---|---|---|---|
| Agent list (with nested `sub_agents`) | `useAgents()` | `/api/v1/agents` | GET |
| Single agent detail (with `sub_agents`, `agent_skills`, `cost_rates`, `capacities`) | `useAgent(id)` | `/api/v1/agents/{id}` | GET |
| Skill catalog (to resolve `agent_skills[].skill_id` → name/version/origin/risk/approval) | `useSkills()` | `/api/v1/agents/skills` | GET |
| Hermes Foundation sync (agents/sub-agents/skills/grants upserted) | `useSyncHermesAgents()` | `/api/v1/agents/sync/hermes-foundation` | POST |
| Description edit | `useUpdateAgent(id)` | `/api/v1/agents/{id}` | PATCH |
| Skill removal (revoke grant) | `useRemoveSkillFromAgent(id)` | `/api/v1/agents/{id}/skills/{agentSkillId}` | DELETE |
| Profile Markdown file content (Soul/Memory/Tools/Agents/Heartbeat/User) | `useProfileFile(slug, filename)` | `/api/v1/foundation/profiles/{slug}/files/{filename}` | GET |
| Profile Markdown file save | `useUpdateProfileFile(slug, filename)` | `/api/v1/foundation/profiles/{slug}/files/{filename}` | PUT |

Hooks defined in `useAgent.ts` but **not called anywhere in these two page files** (verified by grep across `frontend/src/pages/agent/`): `useCreateAgent`, `useDeleteAgent`, `useCreateSubAgent`, `useDeleteSubAgent`, `useAssignSkillToAgent`. See Notes.

## Actions Available

- **Sync from Hermes Foundation** (`index.tsx:63-74`) — button in the list view header, calls `POST /api/v1/agents/sync/hermes-foundation`. This is the only sync trigger found in the codebase; it upserts the `Hermes` coordinator agent, the agent roster (matched by `profile_slug`), sub-agent WORKER/ROLE catalogs, skills (deduped by name+version), and `agent_skills` grants (created with `inheritable=True`) — all from Hermes Foundation's on-disk canonical docs (`backend/app/core/hermes_sync.py`), never from request input. Re-running is safe/idempotent per the route docstring (`backend/app/api/routes/agent.py:169-178`): only Hermes-mirrored fields (`layer`, `runtime_tier`, `telegram_required`, `has_profile`, `mission`, `source_path`) are refreshed on existing agents; manually edited fields (`name`, `status`, `is_active`, `agent_type`, `description`) are left untouched after first creation.
- **View agent** (`index.tsx:213-218`, also per sub-agent row "View parent") — navigates to `/agents/:id`.
- **Edit description** (`[id].tsx:143-176`) — inline textarea + Save/Cancel, calls `PATCH /api/v1/agents/{id}` with `{ description }` only.
- **Remove skill grant** (`[id].tsx:284-293`) — trash icon per skill row, calls `DELETE /api/v1/agents/{id}/skills/{agentSkillId}` (revokes the `agent_skills` association row, not the `Skill` itself).
- **Edit/save profile Markdown file** (`ProfileFilesCard.tsx`) — per-tab textarea + Save button, calls `PUT /api/v1/foundation/profiles/{slug}/files/{filename}`; only enabled when the textarea content differs from the loaded content (`isDirty` check).

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

Citing `docs/BUSINESS_RULES.md` §5 (Skill Rules):

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
- **`ProfileFilesCard` is rendered conditionally on `agent.profile_slug`** (`[id].tsx:188`) — agents created manually (no Hermes sync) or sub-agents have no profile files and thus no way to view/edit a SOUL/MEMORY/etc. doc from this screen; this is by design (those files only exist for Hermes-synced top-level agents) but is worth flagging since it means most of the "detail" richness here only applies to the 25 Hermes-sourced agents, not any future manually-created ones.
- **List view "Layer / Tier" and "Sub-agents count" columns are blank (`—`) for sub-agent rows** (`index.tsx:244-245`) since those columns are agent-only; acceptable given the flattened-table design but slightly redundant given sub-agents already render under their parent.
- **Sync result banner persists across re-syncs** via `syncHermes.isSuccess`/`isError` mutation state — there's no explicit "dismiss" control, so the banner only changes when another sync is triggered or the page is reloaded.
