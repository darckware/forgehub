# Agent Roster Table Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver a canonical, sortable, expandable Agents roster with uploadable photos and correct cleanup/error handling for invalid records.

**Architecture:** Foundation parsing owns roster eligibility, the agent API owns persistence and validation, and a focused React table component owns presentation and URL-backed sorting. Historical non-roster rows are retired; only proven test fixtures are deleted by data migration.

**Tech Stack:** FastAPI, SQLAlchemy 2, Alembic, PostgreSQL, Pydantic 2, React 18, TypeScript, TanStack Query, React Router, Tailwind, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-08-29-agent-roster-table-design.md`

## Global Constraints

- Preserve unrelated work in the primary checkout.
- Keep active application data in the `company` schema.
- Preserve historical operational data for legitimate agents; dependent deletes return HTTP 409.
- Accept agent photos only as JPEG, PNG, or WebP data URLs up to 512 KiB decoded.
- Target WCAG 2.2 AA and preserve pt-BR, English, and Spanish translation parity.
- The active Hermes roster comes from the active Foundation registry, never from directory presence alone.

---

### Task 1: Canonical roster and stale-fixture protection

**Files:**
- Modify: `backend/app/core/hermes_sync.py`
- Modify: `backend/app/api/routes/agent.py`
- Modify: `backend/app/tests/conftest.py`
- Create: `backend/app/tests/test_hermes_sync.py`
- Test: `backend/app/tests/test_agent.py`

**Interfaces:**
- Produces: `list_active_provisioned_profiles() -> list[str]`
- Produces: Foundation sync soft-retires previously synced Hermes rows outside the active set.

- [ ] Write pure failing tests showing archived and undocumented directories are excluded while active registered profiles remain.
- [ ] Run `pytest app/tests/test_hermes_sync.py -q` and confirm the missing selector fails.
- [ ] Implement registry/directory intersection and update sync retirement behavior.
- [ ] Add a failing test for stale fixture cleanup selection, then add session-start/session-end cleanup for exact test signatures.
- [ ] Run the focused backend tests and commit the canonical roster fix.

### Task 2: Avatar persistence and delete conflicts

**Files:**
- Modify: `backend/app/db/models/agent.py`
- Modify: `backend/app/api/schemas/agent.py`
- Modify: `backend/app/api/routes/agent.py`
- Create: `backend/alembic/versions/d4b7e91a2c63_add_agent_avatar_and_clean_roster.py`
- Test: `backend/app/tests/test_agent.py`

**Interfaces:**
- Produces: `Agent.avatar_data_url: str | None`
- Produces: `AgentUpdate.avatar_data_url: str | None`
- Produces: HTTP 409 for an agent delete blocked by retained history.

- [ ] Write failing API/schema tests for valid image data, invalid MIME/base64, oversized data, clearing an avatar, and a dependent-chat delete conflict.
- [ ] Run each focused test and confirm it fails for the missing behavior.
- [ ] Add the model/schema/route behavior and the migration, including narrow cleanup of proven fixture rows and soft retirement of noncanonical synced rows.
- [ ] Re-run the focused tests and commit the backend contract.

### Task 3: Frontend avatar contract and roster data state

**Files:**
- Modify: `frontend/src/hooks/useAgent.ts`
- Modify: `frontend/src/hooks/useAgent.test.ts`
- Create: `frontend/src/components/AgentAvatar.tsx`
- Create: `frontend/src/components/AgentAvatar.test.tsx`

**Interfaces:**
- Produces: parsed `avatar_data_url` on `Agent`.
- Produces: `validateAgentAvatar(file)`, `AgentAvatar`, and update mutation support.

- [ ] Write failing schema and component tests for avatar parsing, initials, allowed formats, size rejection, and removal.
- [ ] Run focused Vitest tests and confirm expected failures.
- [ ] Implement the minimum shared avatar component and validation helpers.
- [ ] Re-run focused tests and commit the frontend avatar contract.

### Task 4: Sortable expandable roster table

**Files:**
- Rewrite: `frontend/src/components/AgentEcosystemHierarchy.tsx`
- Create: `frontend/src/components/AgentRosterTable.test.tsx`
- Modify: `frontend/src/pages/agent/index.tsx`
- Modify: `frontend/src/i18n/locales/pt-BR/agent.json`
- Modify: `frontend/src/i18n/locales/en/agent.json`
- Modify: `frontend/src/i18n/locales/es/agent.json`

**Interfaces:**
- Consumes: `AgentAvatar`, roster data, skills, Telegram status, crons, scripts.
- Produces: native sortable table, URL sort state, and one-at-a-time inline detail rows.

- [ ] Write failing tests for ascending/descending header sort, `aria-sort`, pointer and keyboard expansion, one-open-row behavior, and mutation-error feedback.
- [ ] Run the focused component test and verify RED.
- [ ] Implement the table and reuse the current detail sections inside the expansion row.
- [ ] Add photo upload/replace/remove controls with stable pending and inline error states.
- [ ] Re-run focused tests, translation checks, and commit the table implementation.

### Task 5: Verification and operational cleanup

**Files:**
- Verify: `DESIGN.md`
- Verify: all changed backend/frontend files

**Interfaces:**
- Produces: migration applied to the operational database and evidence that only the canonical active roster is visible.

- [ ] Run Ruff, focused backend tests, full feasible backend suite, Vitest, and `npm run build`.
- [ ] Run DESIGN.md lint and the premium strict audit; resolve blocking findings.
- [ ] Apply the Alembic migration and verify the active roster count and names with a read-only query.
- [ ] Exercise sorting, expansion, avatar upload/removal, delete conflict, loading/error/empty behavior, keyboard access, and a narrow viewport in a real browser.
- [ ] Search changed code for the premium anti-pattern catalog, fix findings, rerun verification, and commit.
