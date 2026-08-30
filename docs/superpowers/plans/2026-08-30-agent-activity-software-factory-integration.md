# Agent Activity and Software Factory Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Finish Agent Activity as the operational projection of the complete Software Factory lifecycle, including conception before a Project exists, version-wide closure readiness, integration into `develop`, push, and deployment.

**Architecture:** Extend the existing additive `forge-agent-activity/v1` read model with canonical conception contexts derived from `DevelopmentRequest`, `ProductConcept`, and `ProductConceptRevision`; never create synthetic projects or parse free-form prose. Keep Agent Activity read-only except for its existing governed/idempotent monitoring command. Align Version Closure's frontend gate with the backend's existing `ProductVersion`-wide task check, then integrate the isolated Agent Activity worktree with the current Software Factory changes.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, Pydantic, PostgreSQL; React 18, TypeScript, TanStack Query, Zod, Tailwind, shadcn/ui, Vitest, React Testing Library, Vite; Git, systemd/development deployment scripts.

**Spec:** `docs/superpowers/specs/2026-08-30-agent-activity-software-factory-integration-design.md`

## Global Constraints

- Preserve all existing changes in both the primary checkout and `feature/agent-activity-continuity` worktree.
- Keep `forge-agent-activity/v1`; API changes are additive.
- Never create a synthetic `Project` for pre-project conception work.
- Build conception relationships only from structured canonical identifiers.
- A ProductVersion can publish only when it has at least one task and every task under every sibling Project is terminal (`done`, `deployed`, or `cancelled`).
- Backend commands remain the final authority for approval, authorization, publication, and deployment.
- Use TDD for behavior changes and commit each independently testable deliverable.
- Push and deploy only after the integrated `develop` branch passes fresh verification.

---

### Task 1: Finish and commit the existing Agent Activity operational views

**Files:**
- Create/commit: `frontend/src/components/agent-activity/ActivityViewSwitch.tsx`
- Create/commit: `frontend/src/components/agent-activity/AgentInspector.tsx`
- Create/commit: `frontend/src/components/agent-activity/CurrentFlowBoard.tsx`
- Create/commit: `frontend/src/components/agent-activity/CurrentFlowBoard.test.tsx`
- Create/commit: `frontend/src/components/agent-activity/ContinuityTimeline.tsx`
- Create/commit: `frontend/src/components/agent-activity/ContinuityTimeline.test.tsx`
- Create/commit: `frontend/src/components/agent-activity/RequestAthosDialog.tsx`
- Create/commit: `frontend/src/components/agent-activity/SeverityInbox.tsx`
- Modify: `frontend/src/pages/agent-activity/index.tsx`
- Modify: `frontend/src/pages/agent-activity/index.test.tsx`
- Modify: `frontend/src/i18n/locales/{en,pt-BR}/agentActivity.json`
- Delete obsolete: `frontend/src/components/AgentActivityStage.tsx`, `frontend/src/components/AgentActivityTasksDialog.tsx`

**Interfaces:**
- Consumes: `AgentActivity`, `ActivityFlowItem`, `ActivityTimelineEvent`, and topology DTOs from `useAgentActivity.ts`.
- Produces: a buildable page with topology, current-flow board, history lanes, incident rail, selected-agent inspector, and monitoring dialog.

- [ ] **Step 1: Run the focused frontend tests and capture every current failure**

Run:

```bash
cd frontend && npm test -- --run src/hooks/useAgentActivity.test.ts src/hooks/useAgentActivityViewModel.test.ts src/components/agent-activity/ActivityTopology.test.tsx src/components/agent-activity/CurrentFlowBoard.test.tsx src/components/agent-activity/ContinuityTimeline.test.tsx src/pages/agent-activity/index.test.tsx
```

Expected: failures identify incomplete page/view integration or missing locale keys; no implementation change occurs before this RED evidence.

- [ ] **Step 2: Complete only the missing component/page behavior**

Wire the page as:

```tsx
<ActivityTopology agents={data.agents} projects={data.projects} resources={data.resources}
  relations={data.topology_relations} edges={data.message_edges} projectScopeId={data.project_id}
  selectedAgentId={effectiveSelectedAgentId} onSelectAgent={setSelectedAgentId} onOpenMessage={openMessage} />
<ActivityViewSwitch value={activeView} onValueChange={setActiveView} />
{activeView === "flow"
  ? <CurrentFlowBoard items={data.flow_items} />
  : <ContinuityTimeline events={data.timeline} selectedAgentId={effectiveSelectedAgentId} />}
```

Keep the monitoring dialog focus trap/restoration tests and remove imports/usages of the obsolete animated stage/task dialog.

- [ ] **Step 3: Run the focused tests and build**

```bash
cd frontend && npm test -- --run src/hooks/useAgentActivity.test.ts src/hooks/useAgentActivityViewModel.test.ts src/components/agent-activity/ActivityTopology.test.tsx src/components/agent-activity/CurrentFlowBoard.test.tsx src/components/agent-activity/ContinuityTimeline.test.tsx src/pages/agent-activity/index.test.tsx
cd frontend && npm run build
```

Expected: all focused tests pass and Vite exits 0.

- [ ] **Step 4: Commit the finished operational views**

```bash
git add frontend/src/components/agent-activity frontend/src/pages/agent-activity frontend/src/i18n/locales/en/agentActivity.json frontend/src/i18n/locales/pt-BR/agentActivity.json frontend/src/components/AgentActivityStage.tsx frontend/src/components/AgentActivityTasksDialog.tsx
git commit -m "Agent Activity: finish operational views"
```

---

### Task 2: Add canonical pre-project conception contexts to the backend

**Files:**
- Modify: `backend/app/api/schemas/agent_activity.py`
- Modify: `backend/app/core/agent_activity.py`
- Test: `backend/app/tests/test_agent_activity.py`

**Interfaces:**
- Produces `ActivityContextOut` with `context_kind`, canonical conception/project identifiers, product identity, status, title, timestamps, and canonical path.
- Adds defaulted `contexts` to `AgentActivityOut` and nullable context identifiers to current work, flow items, incidents, and timeline events.

- [ ] **Step 1: Write failing backend tests**

Add tests that create a `DevelopmentRequest`, `ProductConcept`, and current `ProductConceptRevision` with no `Project`, then assert:

```python
assert result.contexts[0].context_kind == "conception"
assert result.contexts[0].development_request_id == request.id
assert result.contexts[0].concept_id == concept.id
assert result.contexts[0].project_id is None
assert any(item.source_type == "product_concept" and item.context_id == concept.id for item in result.flow_items)
```

Add a transition case where authorization creates two projects under the ProductVersion; assert one conception history remains and both project contexts reference the same conception identifiers without duplicate source keys.

- [ ] **Step 2: Run the focused tests and verify RED**

```bash
cd backend && /root/project/forgehub/backend/.venv/bin/pytest app/tests/test_agent_activity.py -k "conception_context or conception_transition" -v
```

Expected: schema/import/assertion failure because context DTOs and aggregation do not exist.

- [ ] **Step 3: Implement the additive contract and bounded queries**

Define:

```python
class ActivityContextOut(BaseModel):
    context_kind: Literal["conception", "project"]
    context_id: uuid.UUID
    product_id: uuid.UUID
    product_name: str
    development_request_id: uuid.UUID | None = None
    concept_id: uuid.UUID | None = None
    concept_revision_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    project_name: str | None = None
    working_directory_path: str | None = None
    title: str
    status: str
    canonical_path: str
    created_at: datetime
    updated_at: datetime
```

Load recent active conception records by timestamp, product, and optional context filter. Join projects to products through `ProductVersion.product_id`; use `SystemBlueprintRevision.product_version_id` plus `concept_revision_id` when available to preserve exact lineage. Do not inspect `AgentDemand.body`, subject text, or other prose.

- [ ] **Step 4: Emit conception flow and planning-history items**

Map concept statuses deterministically: `draft -> planning`, `in_review|hold|rework -> attention`, `approved -> completed`, `rejected|superseded -> archived`. Emit stable keys `product-concept:<uuid>` and planning-lane timeline entries linked to `/conception`.

- [ ] **Step 5: Run backend verification and commit**

```bash
cd backend && /root/project/forgehub/backend/.venv/bin/pytest app/tests/test_agent_activity.py -v
cd backend && /root/project/forgehub/backend/.venv/bin/ruff check app/api/schemas/agent_activity.py app/core/agent_activity.py app/tests/test_agent_activity.py
git add backend/app/api/schemas/agent_activity.py backend/app/core/agent_activity.py backend/app/tests/test_agent_activity.py
git commit -m "Agent Activity: project conception contexts"
```

---

### Task 3: Render conception contexts in Agent Activity

**Files:**
- Modify: `frontend/src/hooks/useAgentActivity.ts`
- Modify: `frontend/src/hooks/useAgentActivity.test.ts`
- Modify: `frontend/src/hooks/useAgentActivityViewModel.ts`
- Modify: `frontend/src/hooks/useAgentActivityViewModel.test.ts`
- Modify: `frontend/src/components/agent-activity/ActivityTopology.tsx`
- Modify: `frontend/src/components/agent-activity/TopologyNode.tsx`
- Modify: `frontend/src/components/agent-activity/AgentInspector.tsx`
- Modify: `frontend/src/components/agent-activity/CurrentFlowBoard.tsx`
- Modify: `frontend/src/pages/agent-activity/index.test.tsx`
- Modify: `frontend/src/i18n/locales/{en,pt-BR}/agentActivity.json`

**Interfaces:**
- Consumes backend `contexts` and nullable context references.
- Produces conception nodes/cards labelled as Conception, accessible text relationships, and conception-to-project continuity.

- [ ] **Step 1: Write failing Zod, view-model, and page tests**

Assert the schema accepts a conception with no project and rejects invalid `context_kind`. Assert the graph builds a `conception:<uuid>` node, the page announces `Concepção`, and approved transition fixtures show both the preserved conception and two real projects.

- [ ] **Step 2: Run tests and verify RED**

```bash
cd frontend && npm test -- --run src/hooks/useAgentActivity.test.ts src/hooks/useAgentActivityViewModel.test.ts src/pages/agent-activity/index.test.tsx
```

- [ ] **Step 3: Implement schemas and UI using existing shared primitives**

Add exact Zod literals and nullable IDs. Extend graph node kinds with `conception`; use a `Lightbulb` icon plus visible `Conception`/`Concepção` text. Keep nodes as real buttons and list every conception relationship in the textual relationship region.

- [ ] **Step 4: Run focused frontend verification and commit**

```bash
cd frontend && npm test -- --run src/hooks/useAgentActivity.test.ts src/hooks/useAgentActivityViewModel.test.ts src/components/agent-activity/ActivityTopology.test.tsx src/pages/agent-activity/index.test.tsx
cd frontend && npm run build
git add frontend/src/hooks/useAgentActivity.ts frontend/src/hooks/useAgentActivity.test.ts frontend/src/hooks/useAgentActivityViewModel.ts frontend/src/hooks/useAgentActivityViewModel.test.ts frontend/src/components/agent-activity frontend/src/pages/agent-activity/index.test.tsx frontend/src/i18n/locales/en/agentActivity.json frontend/src/i18n/locales/pt-BR/agentActivity.json
git commit -m "Agent Activity: show conception work"
```

---

### Task 4: Align Version Closure with ProductVersion-wide readiness

**Files:**
- Modify: `frontend/src/pages/version-closure/index.tsx`
- Create or modify: `frontend/src/pages/version-closure/index.test.tsx`
- Modify only if coverage reveals a server defect: `backend/app/api/routes/product.py`
- Test: `backend/app/tests/test_product.py`

**Interfaces:**
- Consumes projects, planning items, and tasks already loaded by the Version Closure page.
- Produces version-wide totals, grouped blockers, and a frontend gate identical to `POST /api/v1/products/versions/{id}:publish`.

- [ ] **Step 1: Write a failing multi-project frontend test**

Fixture: one version with Project A fully done and Project B with one planned task. Select Project A and assert the publish control remains disabled, the summary says two projects, and Project B's task is visible as the blocker.

- [ ] **Step 2: Strengthen the existing backend regression test first**

Extend `test_publish_version_blocks_on_unfinished_tasks` to create a completed task in one project and a pending task in a sibling project. Verify `409.detail.blocking` names only the pending sibling task, then finish it and verify both projects become `completed` after publication.

- [ ] **Step 3: Run both tests and verify frontend RED/backend GREEN**

```bash
cd backend && /root/project/forgehub/backend/.venv/bin/pytest app/tests/test_product.py::test_publish_version_blocks_on_unfinished_tasks -v
cd frontend && npm test -- --run src/pages/version-closure/index.test.tsx
```

- [ ] **Step 4: Implement version-wide derivation in the page**

Compute `versionProjects`, `versionTasks`, `completedVersionTasks`, and `pendingVersionTasks` from the active version. Use those aggregates for readiness, progress, blocker groups, and the publish button. Keep selected-project detail independent. Require `versionTasks.length > 0 && pendingVersionTasks.length === 0`.

- [ ] **Step 5: Run focused tests/build and commit**

```bash
cd backend && /root/project/forgehub/backend/.venv/bin/pytest app/tests/test_product.py::test_publish_version_blocks_on_unfinished_tasks -v
cd frontend && npm test -- --run src/pages/version-closure/index.test.tsx
cd frontend && npm run build
git add backend/app/tests/test_product.py frontend/src/pages/version-closure/index.tsx frontend/src/pages/version-closure/index.test.tsx
git commit -m "Software Factory: gate version-wide closure"
```

---

### Task 4A: Link Messages, Software Factory, and Agent Activity canonically

**Files:**
- Modify: `backend/app/db/models/demand.py`
- Modify: `backend/app/api/schemas/demand.py`
- Modify: `backend/app/api/routes/demand.py`
- Create: `backend/alembic/versions/e5c8a12f4d90_link_messages_to_development_requests.py`
- Test: `backend/app/tests/test_messages_factory_context.py`
- Modify: `backend/app/api/schemas/agent_activity.py`, `backend/app/core/agent_activity.py`
- Modify: `frontend/src/hooks/useDemands.ts`, `frontend/src/pages/demands/DemandFormPanel.tsx`
- Modify: `host-bridge/forgehub_messages_mcp.py`

- [x] **Step 1: Add RED tests for canonical conception/project coherence and projection**
- [x] **Step 2: Add `AgentDemand.development_request_id` with an additive foreign key migration**
- [x] **Step 3: Validate that linked request and project belong to the same product**
- [x] **Step 4: Project the structured context in Agent Activity and expose it in Messages UI/MCP**
- [x] **Step 5: Run focused backend/frontend verification**

---

### Task 5: Reconcile the premium UI remediation without widening product behavior

**Files:**
- Commit existing scoped changes in: `frontend/src/components/ui/button.tsx`, `frontend/src/components/ui/confirm-dialog.tsx`, `frontend/src/components/ui/confirm-dialog.test.tsx`, `frontend/src/components/ui/textarea.tsx`, `frontend/src/index.css`, `UX-CONTRACT.md`, `premium-ui.json`
- Review every other modified frontend file and retain only mechanical adoption of shared confirmation, textarea, cursor/focus, or scrollbar contracts.

**Interfaces:**
- Produces one shared confirmation and interaction contract used consistently by Software Factory and Agent Activity.

- [ ] **Step 1: Inspect the complete diff and run anti-pattern searches**

```bash
git diff -- frontend/src UX-CONTRACT.md premium-ui.json
rg -n "window\.(alert|confirm|prompt)|\b(alert|confirm|prompt)\(" frontend/src
```

Reject unrelated product changes; preserve existing user/agent work in a separate patch/commit if it is valid but outside this integration.

- [ ] **Step 2: Run shared component tests and strict audit**

```bash
cd frontend && npm test -- --run src/components/ui/confirm-dialog.test.tsx
python /root/.codex/plugins/cache/openai-curated-remote/frontend-design-premium/1.4.0/skills/frontend-design-premium/scripts/audit_project.py . --mode strict --no-write
```

- [ ] **Step 3: Commit the verified shared remediation**

```bash
git add UX-CONTRACT.md premium-ui.json frontend/src/components/ui/button.tsx frontend/src/components/ui/confirm-dialog.tsx frontend/src/components/ui/confirm-dialog.test.tsx frontend/src/components/ui/textarea.tsx frontend/src/index.css
git add -u frontend/src
git commit -m "Design: enforce shared interaction contracts"
```

---

### Task 6: Integrate, verify, push, deploy, and smoke test

**Files:**
- Merge: `feature/agent-activity-continuity` into `develop`
- Preserve and commit current Software Factory files in the primary checkout.
- Modify only files required to resolve verified merge conflicts.

**Interfaces:**
- Produces an integrated `develop` revision deployed through the repository's established path.

- [ ] **Step 1: Validate and commit the primary checkout's Software Factory work**

Run `git diff --check`, Ruff, focused Software Factory backend tests, frontend tests, and build. Fix only confirmed failures, then commit the current Software Factory batch separately.

- [ ] **Step 2: Merge the feature branch into `develop`**

```bash
git merge --no-ff feature/agent-activity-continuity
```

Resolve overlapping Conception, Cockpit, Version Closure, shared UI, locale, and documentation files by preserving the latest Software Factory domain behavior plus Agent Activity's new read model and interaction contract.

- [ ] **Step 3: Run fresh integrated verification**

```bash
git diff --check
cd backend && /root/project/forgehub/backend/.venv/bin/ruff check app
cd backend && /root/project/forgehub/backend/.venv/bin/pytest
cd frontend && npm test -- --run
cd frontend && npm run build
python /root/.codex/plugins/cache/openai-curated-remote/frontend-design-premium/1.4.0/skills/frontend-design-premium/scripts/audit_project.py . --mode strict --no-write
```

- [ ] **Step 4: Browser-smoke the integrated application**

Verify authenticated `/agent-activity`, conception without project, conception-to-project transition fixtures/data, `/version-closure` with sibling blockers, `/conception`, `/projects`, Governance, and Cockpit at desktop and narrow widths. Verify keyboard focus, monitoring confirmation, reduced motion, loading/error states, and EN/PT-BR labels.

- [ ] **Step 5: Commit integration fixes and push**

```bash
git add -u
git add backend/app/mcp/factory_server.py docs/modules/SOFTWARE_FACTORY_PIPELINE.md
git commit -m "Agent Activity: integrate software factory"
git push origin develop
```

- [ ] **Step 6: Deploy the pushed revision and verify**

Use the repository's documented deployment/service command discovered from `docs/`, service definitions, and current runtime status. Record the deployed commit. Apply Alembic only if `alembic current` differs from `head`. Verify backend health, frontend response, authenticated Agent Activity, Version Closure gate, and service status after restart.

- [ ] **Step 7: Publish durable verified knowledge**

Publish a redacted candidate through `knowledge_cycle.py publish` describing the canonical conception projection, version-wide closure invariant, deployed revision, and verification evidence. Never include secrets or raw private conversation.
