# Agent Activity Operational Views Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Present canonical agents, projects, database usage, current processing stages, and continuity history through an accessible interactive Agent Activity screen.

**Architecture:** Extend the existing additive Agent Activity read model so the backend owns project/resource relationships, flow-stage normalization, and history-lane semantics. The React client validates that contract, renders a pointer/keyboard-movable topology with browser-local coordinates, and provides separate current-flow and historical views without creating a second workflow.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, Pydantic, PostgreSQL; React 18, TypeScript, Vite, TanStack Query, Zod, Tailwind, shadcn/ui, Framer Motion, Vitest, React Testing Library.

**Spec:** `docs/superpowers/specs/2026-08-30-agent-activity-operational-views-design.md`

## Global Constraints

- Keep `forge-agent-activity/v1`; all API changes are additive.
- Read project, agent, membership, task, execution, message, approval, checkpoint, and notification facts from existing `company` schema records only.
- Represent `company_postgres` / `company` as a read-only topology resource; do not create a database record or migration.
- Solid agent-project relations mean current execution; dashed relations mean active membership without current execution.
- Persist only normalized node coordinates in versioned, project-filter-scoped `localStorage`.
- Preserve original `source_type` and `source_status` on every normalized flow item.
- Support English and Brazilian Portuguese, visible keyboard focus, text equivalents for graph edges, and reduced motion.
- Use TDD for each behavior and keep the development stack available at the established worktree ports.

---

### Task 1: Add canonical topology records to the backend read model

**Files:**
- Modify: `backend/app/api/schemas/agent_activity.py`
- Modify: `backend/app/core/agent_activity.py`
- Test: `backend/app/tests/test_agent_activity.py`

**Interfaces:**
- Consumes: `Agent.avatar_data_url`, `Project`, `ProjectAgentMembership`, `ActivityCurrentWorkOut.project_id`.
- Produces: `ActivityProjectOut`, `ActivityResourceOut`, `ActivityTopologyRelationOut`, `ActivityAgentOut.avatar_data_url`, and `AgentActivityOut.projects/resources/topology_relations`.

- [ ] **Step 1: Write failing schema and aggregation tests**

Add a contract test that constructs the new typed objects and an async aggregation test with one current execution, one membership-only project, and one inactive membership:

```python
def test_agent_activity_contract_serializes_topology_objects():
    view = AgentActivityOut(
        generated_at=NOW,
        project_id=None,
        agents=[activity_agent(avatar_data_url="data:image/png;base64,AA==")],
        projects=[ActivityProjectOut(id=PROJECT_ID, name="ForgeHub", status="active", canonical_path=f"/projects/{PROJECT_ID}")],
        resources=[ActivityResourceOut(key="database:company_postgres/company", kind="database", label="company_postgres", detail="company", status="available")],
        topology_relations=[
            ActivityTopologyRelationOut(
                key=f"current-work:{AGENT_ID}:{PROJECT_ID}",
                kind="current_work",
                from_type="agent",
                from_id=str(AGENT_ID),
                to_type="project",
                to_id=str(PROJECT_ID),
                label="Working now",
            )
        ],
        flow_items=[], message_edges=[], incidents=[], timeline=[], source_freshness=[],
    )
    payload = view.model_dump(mode="json")
    assert payload["agents"][0]["avatar_data_url"].startswith("data:image/png")
    assert payload["topology_relations"][0]["kind"] == "current_work"
```

In the database-backed test, assert that the current relation replaces the membership relation for the same agent/project pair, membership-only projects remain visible, inactive memberships are absent, and the resource key is stable.

- [ ] **Step 2: Run the focused tests and verify failure**

Run:

```bash
cd backend && .venv/bin/pytest app/tests/test_agent_activity.py -k "topology_objects or project_relationships" -v
```

Expected: collection or assertion failure because the topology DTOs and fields do not exist.

- [ ] **Step 3: Add the additive Pydantic contract**

Define exact DTOs and defaults:

```python
class ActivityProjectOut(BaseModel):
    id: uuid.UUID
    name: str
    status: str
    canonical_path: str

class ActivityResourceOut(BaseModel):
    key: str
    kind: Literal["database"]
    label: str
    detail: str | None = None
    status: Literal["available", "degraded", "unavailable"]

class ActivityTopologyRelationOut(BaseModel):
    key: str
    kind: Literal["current_work", "membership", "persistence"]
    from_type: Literal["agent", "project"]
    from_id: str
    to_type: Literal["project", "resource"]
    to_id: str
    label: str
```

Add `avatar_data_url: str | None = None` to `ActivityAgentOut`, and defaulted lists to `AgentActivityOut` so older test constructors remain valid:

```python
projects: list[ActivityProjectOut] = Field(default_factory=list)
resources: list[ActivityResourceOut] = Field(default_factory=list)
topology_relations: list[ActivityTopologyRelationOut] = Field(default_factory=list)
```

- [ ] **Step 4: Aggregate projects, resources, and deduplicated relations**

Load active `ProjectAgentMembership` rows for visible agents and the selected project scope. Load any additional referenced projects in the existing project query. Build stable relations with current work taking precedence:

```python
relation_by_pair[(str(agent_id), str(project_id))] = ActivityTopologyRelationOut(
    key=f"membership:{agent_id}:{project_id}",
    kind="membership",
    from_type="agent",
    from_id=str(agent_id),
    to_type="project",
    to_id=str(project_id),
    label="Allocated",
)
for agent in activity_agents:
    if agent.current_work and agent.current_work.project_id:
        project_key = str(agent.current_work.project_id)
        relation_by_pair[(str(agent.id), project_key)] = ActivityTopologyRelationOut(
            key=f"current-work:{agent.id}:{project_key}",
            kind="current_work",
            from_type="agent",
            from_id=str(agent.id),
            to_type="project",
            to_id=project_key,
            label="Working now",
        )
```

Create one persistence relation per visible project to `database:company_postgres/company`. Derive resource availability from whether the database-backed aggregation completed; never inspect or serialize the connection URL.

- [ ] **Step 5: Run backend tests and lint**

Run:

```bash
cd backend && .venv/bin/pytest app/tests/test_agent_activity.py -v
cd backend && /root/project/forgehub/backend/.venv/bin/ruff check app/api/schemas/agent_activity.py app/core/agent_activity.py app/tests/test_agent_activity.py
```

Expected: all Agent Activity tests pass and Ruff reports no findings.

- [ ] **Step 6: Commit the topology contract**

```bash
git add backend/app/api/schemas/agent_activity.py backend/app/core/agent_activity.py backend/app/tests/test_agent_activity.py
git commit -m "Agent Activity: expose topology resources"
```

---

### Task 2: Normalize current-flow stages and history lanes on the backend

**Files:**
- Modify: `backend/app/api/schemas/agent_activity.py`
- Modify: `backend/app/core/agent_activity.py`
- Test: `backend/app/tests/test_agent_activity.py`

**Interfaces:**
- Consumes: canonical demand, task execution, checkpoint, approval, and notification statuses already loaded by `build_agent_activity`.
- Produces: `ActivityFlowItemOut`, `build_flow_items(...)`, `ActivityTimelineEventOut.lane`, `ActivityTimelineEventOut.source_status`, and `AgentActivityOut.flow_items`.

- [ ] **Step 1: Write failing table-driven classification tests**

Use explicit examples that guard domain boundaries:

```python
@pytest.mark.parametrize(
    ("source_type", "source_status", "expected"),
    [
        ("agent_demand", "new", "incoming"),
        ("agent_demand", "dispatched", "queued"),
        ("task_execution", "pending", "queued"),
        ("task_execution", "running", "executing"),
        ("task_execution", "reported", "verifying"),
        ("task_execution", "failed", "attention"),
        ("approval_request", "pending", "attention"),
        ("agent_demand", "archived", "archived"),
    ],
)
def test_classify_flow_stage(source_type, source_status, expected):
    assert classify_flow_stage(source_type, source_status) == expected
```

Add an aggregation assertion that each canonical source identity occurs at most once in `flow_items`, with failure/blocked precedence.

- [ ] **Step 2: Run focused classification tests and verify failure**

```bash
cd backend && .venv/bin/pytest app/tests/test_agent_activity.py -k "classify_flow_stage or flow_items or history_lane" -v
```

Expected: failure because flow classification and lane fields are absent.

- [ ] **Step 3: Define the flow DTO and display enums**

```python
ActivityFlowStage = Literal[
    "incoming", "planning", "queued", "executing",
    "verifying", "completed", "attention", "archived",
]

class ActivityFlowItemOut(BaseModel):
    key: str
    stage: ActivityFlowStage
    source_type: str
    source_id: uuid.UUID
    source_status: str
    title: str
    occurred_at: datetime
    updated_at: datetime
    canonical_path: str
    agent_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    execution_id: uuid.UUID | None = None
```

Add `flow_items: list[ActivityFlowItemOut] = Field(default_factory=list)` to `AgentActivityOut`. Add `lane: Literal["communication", "planning", "execution", "checkpoint", "governance"]` and `source_status: str` to `ActivityTimelineEventOut`.

- [ ] **Step 4: Implement explicit stage and lane mapping**

Use source-aware maps rather than one global status map:

```python
FLOW_STAGE_BY_SOURCE = {
    "agent_demand": {
        "new": "incoming", "read": "incoming", "incubating": "planning",
        "decision_pending": "attention", "dispatched": "queued",
        "running": "executing", "completed": "completed",
        "failed": "attention", "archived": "archived",
    },
    "task_execution": {
        "pending": "queued", "running": "executing", "reported": "verifying",
        "verified": "verifying", "completed": "completed", "failed": "attention",
        "retried": "queued",
    },
    "approval_request": {"pending": "attention", "approved": "completed", "rejected": "attention"},
}
```

For messages, choose the most operational status in this order: failed, running, dispatched, archived, then inbox status. Build one item per message, one per execution, and one per pending approval. Notifications and checkpoints remain historical facts and do not create duplicate flow cards.

- [ ] **Step 5: Add lanes and source statuses to every timeline builder branch**

Use `communication` for demand/notification, `execution` for execution, `checkpoint` for checkpoint, and `governance` for approval. Preserve actual status strings (`dispatch_status or status`, execution status, checkpoint type, approval status, notification severity/category) in `source_status`.

- [ ] **Step 6: Run focused and complete backend verification**

```bash
cd backend && .venv/bin/pytest app/tests/test_agent_activity.py -v
cd backend && /root/project/forgehub/backend/.venv/bin/ruff check app/api/schemas/agent_activity.py app/core/agent_activity.py app/tests/test_agent_activity.py
```

Expected: tests pass; the serialized read model includes deterministic `flow_items` and lane-tagged history.

- [ ] **Step 7: Commit flow semantics**

```bash
git add backend/app/api/schemas/agent_activity.py backend/app/core/agent_activity.py backend/app/tests/test_agent_activity.py
git commit -m "Agent Activity: classify operational flow"
```

---

### Task 3: Validate the new contract and build a reusable graph view model

**Files:**
- Modify: `frontend/src/hooks/useAgentActivity.ts`
- Modify: `frontend/src/hooks/useAgentActivity.test.ts`
- Modify: `frontend/src/hooks/useAgentActivityViewModel.ts`
- Create: `frontend/src/hooks/useAgentActivityViewModel.test.ts`

**Interfaces:**
- Consumes: backend fields from Tasks 1–2.
- Produces: `ActivityGraphNode`, `ActivityGraphEdge`, `layoutActivityGraph`, `clampGraphPosition`, `mergeSavedGraphPositions`, and Zod-inferred topology/flow types.

- [ ] **Step 1: Extend the frontend fixture and write failing schema tests**

Add `avatar_data_url`, `projects`, `resources`, `topology_relations`, `flow_items`, and timeline `lane/source_status` to `ACTIVITY`. Assert malformed endpoint types and unsupported stages are rejected:

```typescript
expect(() => agentActivitySchema.parse({
  ...ACTIVITY,
  topology_relations: [{ ...ACTIVITY.topology_relations[0], to_type: "agent" }],
})).toThrow();
expect(() => agentActivitySchema.parse({
  ...ACTIVITY,
  flow_items: [{ ...ACTIVITY.flow_items[0], stage: "mystery" }],
})).toThrow();
```

- [ ] **Step 2: Run schema tests and verify failure**

```bash
cd frontend && npm test -- --run src/hooks/useAgentActivity.test.ts
```

Expected: fixtures/types fail until the new schemas are defined.

- [ ] **Step 3: Add exact Zod schemas**

Mirror the backend literals and export inferred types. Keep every newly required server list required in the frontend schema so malformed deployments fail visibly instead of silently removing graph content.

```typescript
export const activityFlowStageSchema = z.enum([
  "incoming", "planning", "queued", "executing",
  "verifying", "completed", "attention", "archived",
]);
```

- [ ] **Step 4: Write failing graph layout and persistence tests**

Cover stable output regardless of input order, distinct zones for agents/projects/resources, coordinate clamping, stale saved-node removal, new-node defaults, and project-filter storage keys:

```typescript
expect(clampGraphPosition({ xPct: -4, yPct: 108 })).toEqual({ xPct: 4, yPct: 94 });
expect(graphPositionStorageKey(null)).toBe("forgehub:agent-activity:topology:v1:all");
expect(graphPositionStorageKey(IDS.project)).toContain(IDS.project);
```

- [ ] **Step 5: Run view-model tests and verify failure**

```bash
cd frontend && npm test -- --run src/hooks/useAgentActivityViewModel.test.ts
```

Expected: failure because the graph helpers do not exist.

- [ ] **Step 6: Implement deterministic layout and saved-position reconciliation**

Define nodes with `id`, `kind`, `label`, `xPct`, and `yPct`. Prefix IDs as `agent:<uuid>`, `project:<uuid>`, and use the resource key directly. Place agents in the upper/outer band, projects in a middle band, and resources in a lower/central band. Clamp x to `4..96` and y to `6..94`. Apply saved coordinates only after validating finite numbers and known node IDs.

- [ ] **Step 7: Run hook and view-model tests**

```bash
cd frontend && npm test -- --run src/hooks/useAgentActivity.test.ts src/hooks/useAgentActivityViewModel.test.ts
```

Expected: both files pass.

- [ ] **Step 8: Commit client contract and graph model**

```bash
git add frontend/src/hooks/useAgentActivity.ts frontend/src/hooks/useAgentActivity.test.ts frontend/src/hooks/useAgentActivityViewModel.ts frontend/src/hooks/useAgentActivityViewModel.test.ts
git commit -m "Agent Activity: model interactive topology"
```

---

### Task 4: Render movable agent, project, and database nodes

**Files:**
- Modify: `frontend/src/components/agent-activity/ActivityTopology.tsx`
- Create: `frontend/src/components/agent-activity/ActivityTopology.test.tsx`
- Create: `frontend/src/components/agent-activity/TopologyNode.tsx`
- Create: `frontend/src/components/agent-activity/useTopologyPositions.ts`
- Modify: `frontend/src/i18n/locales/en/agentActivity.json`
- Modify: `frontend/src/i18n/locales/pt-BR/agentActivity.json`

**Interfaces:**
- Consumes: Task 3 graph helpers and types; shared `AgentAvatar`.
- Produces: interactive `ActivityTopology` accepting `agents`, `projects`, `resources`, `relations`, `edges`, and `projectScopeId`.

- [ ] **Step 1: Write failing component interaction tests**

Test registered avatar rendering, initials fallback, project/database accessible names, relation text, pointer movement persistence, arrow-key movement, Shift larger step, and Organize reset. Stub element bounds so pointer math is deterministic:

```typescript
fireEvent.keyDown(screen.getByRole("button", { name: /ForgeHub.*project/i }), { key: "ArrowRight" });
expect(screen.getByRole("status")).toHaveTextContent(/moved/i);
await user.click(screen.getByRole("button", { name: /organize/i }));
expect(localStorage.getItem("forgehub:agent-activity:topology:v1:all")).toBeNull();
```

- [ ] **Step 2: Run the component test and verify failure**

```bash
cd frontend && npm test -- --run src/components/agent-activity/ActivityTopology.test.tsx
```

Expected: failure because resource nodes, movement, and Organize do not exist.

- [ ] **Step 3: Extract a focused topology node**

`TopologyNode` renders type-specific icon/content while sharing pointer and keyboard mechanics. Agent content uses:

```tsx
<AgentAvatar
  name={agent.name}
  avatarDataUrl={agent.avatar_data_url}
  size="sm"
  className={AVAILABILITY_CLASS[agent.availability]}
/>
```

Project nodes use a folder/repository icon and lifecycle status. Resource nodes use `Database` with resource detail.

- [ ] **Step 4: Implement local position ownership**

`useTopologyPositions` loads validated coordinates once per scope, reconciles them when node identities change, writes after a completed move, and exposes:

```typescript
{
  positions,
  moveNode(id: string, position: GraphPosition): void,
  organize(): void,
}
```

Do not persist during every pointer frame; update React state during movement and write the settled map on pointer-up.

- [ ] **Step 5: Render graph relations and accessible equivalents**

Render `current_work` as solid, `membership` as dashed, and `persistence` as a muted solid line. Preserve message arrows and packets. Add a relationship list whose entries identify endpoints and relation kind, including message links. Ensure edge coordinates follow moved node positions.

- [ ] **Step 6: Add pointer, keyboard, and Organize behavior**

Use pointer capture and a movement threshold to distinguish dragging from clicking. Arrow keys move 1 percentage point and Shift+Arrow moves 5. The Organize button calls `organize()`, clears the scoped key, and reports completion through a polite live region.

- [ ] **Step 7: Run topology and existing page tests**

```bash
cd frontend && npm test -- --run src/components/agent-activity/ActivityTopology.test.tsx src/pages/agent-activity/index.test.tsx
```

Expected: graph behavior passes and existing selection/message behavior remains intact.

- [ ] **Step 8: Commit the interactive topology**

```bash
git add frontend/src/components/agent-activity/ActivityTopology.tsx frontend/src/components/agent-activity/ActivityTopology.test.tsx frontend/src/components/agent-activity/TopologyNode.tsx frontend/src/components/agent-activity/useTopologyPositions.ts frontend/src/i18n/locales/en/agentActivity.json frontend/src/i18n/locales/pt-BR/agentActivity.json
git commit -m "Agent Activity: add movable topology objects"
```

---

### Task 5: Add the current-flow board and readable history lanes

**Files:**
- Create: `frontend/src/components/agent-activity/ActivityViewSwitch.tsx`
- Create: `frontend/src/components/agent-activity/CurrentFlowBoard.tsx`
- Create: `frontend/src/components/agent-activity/CurrentFlowBoard.test.tsx`
- Modify: `frontend/src/components/agent-activity/ContinuityTimeline.tsx`
- Create: `frontend/src/components/agent-activity/ContinuityTimeline.test.tsx`
- Modify: `frontend/src/i18n/locales/en/agentActivity.json`
- Modify: `frontend/src/i18n/locales/pt-BR/agentActivity.json`

**Interfaces:**
- Consumes: `ActivityFlowItem[]` and lane-tagged `ActivityTimelineEvent[]` from Task 3.
- Produces: `ActivityViewSwitch`, `CurrentFlowBoard`, and swimlane `ContinuityTimeline`.

- [ ] **Step 1: Write failing flow-board tests**

Assert fixed stage ordering, original source status visibility, empty columns with counts, canonical links, and attention styling with a text label:

```typescript
expect(screen.getAllByRole("heading", { level: 3 }).map((node) => node.textContent)).toEqual([
  "Entrada", "Planejamento", "Fila", "Execução", "Verificação", "Concluído", "Atenção", "Arquivado",
]);
expect(screen.getByRole("link", { name: /Build release.*failed/i })).toHaveAttribute("href", "/tasks/...");
```

- [ ] **Step 2: Write failing history-lane tests**

Assert lane order, chronological order inside each lane across timezone offsets, readable card minimum width, selected-agent emphasis with screen-reader text, and canonical links.

- [ ] **Step 3: Run both component tests and verify failure**

```bash
cd frontend && npm test -- --run src/components/agent-activity/CurrentFlowBoard.test.tsx src/components/agent-activity/ContinuityTimeline.test.tsx
```

Expected: failure because the flow board does not exist and history is still a single compressed row.

- [ ] **Step 4: Implement the read-only current-flow board**

Use the fixed stage array as the only display order. Group without mutating input, show count badges and original `source_type · source_status`, and use `min-w-56` cards inside horizontally scrollable columns. Do not add card dragging because this view cannot mutate canonical state.

- [ ] **Step 5: Reshape history into semantic swimlanes**

Group by the five contract lanes and render each as a labelled row with an ordered list. Sort by `Date.parse(occurred_at)` then stable `key`. Use a fixed card width (`w-56 shrink-0`) so long histories scroll rather than compress.

- [ ] **Step 6: Implement the two-view switch**

Use an accessible tablist with `flow` and `history`. Persist only the chosen string under `forgehub:agent-activity:view:v1`; invalid values fall back to `flow`.

- [ ] **Step 7: Run component tests**

```bash
cd frontend && npm test -- --run src/components/agent-activity/CurrentFlowBoard.test.tsx src/components/agent-activity/ContinuityTimeline.test.tsx
```

Expected: both components pass with localized labels and canonical links.

- [ ] **Step 8: Commit operational views**

```bash
git add frontend/src/components/agent-activity/ActivityViewSwitch.tsx frontend/src/components/agent-activity/CurrentFlowBoard.tsx frontend/src/components/agent-activity/CurrentFlowBoard.test.tsx frontend/src/components/agent-activity/ContinuityTimeline.tsx frontend/src/components/agent-activity/ContinuityTimeline.test.tsx frontend/src/i18n/locales/en/agentActivity.json frontend/src/i18n/locales/pt-BR/agentActivity.json
git commit -m "Agent Activity: separate flow from history"
```

---

### Task 6: Integrate the operational views into the page

**Files:**
- Modify: `frontend/src/pages/agent-activity/index.tsx`
- Modify: `frontend/src/pages/agent-activity/index.test.tsx`
- Modify: `DESIGN.md`

**Interfaces:**
- Consumes: all components and contract types from Tasks 3–5.
- Produces: final Agent Activity page composition and durable visual guidance.

- [ ] **Step 1: Update the page fixture and write failing integration tests**

Assert that the page passes all graph collections and scope to topology, defaults to current flow, switches to history, preserves selected-agent emphasis, and retains loading/error geometry:

```typescript
expect(screen.getByRole("tab", { name: /current flow|fluxo atual/i })).toHaveAttribute("aria-selected", "true");
await user.click(screen.getByRole("tab", { name: /history|histórico/i }));
expect(screen.getByRole("region", { name: /continuity history|histórico de continuidade/i })).toBeVisible();
```

- [ ] **Step 2: Run the page test and verify failure**

```bash
cd frontend && npm test -- --run src/pages/agent-activity/index.test.tsx
```

Expected: failure until the new props and view switch are integrated.

- [ ] **Step 3: Integrate topology and operational view state**

Pass `data.projects`, `data.resources`, `data.topology_relations`, and `data.project_id` to `ActivityTopology`. Render the tab switch and only the selected `CurrentFlowBoard` or `ContinuityTimeline`, while keeping Severity Inbox and Agent Inspector unchanged.

- [ ] **Step 4: Update durable design context**

Add an Agent Activity section to `DESIGN.md` documenting the three-view distinction, solid/current versus dashed/allocation edges, graph movement boundaries, fixed-width history cards, and the rule that display stages never replace canonical statuses.

- [ ] **Step 5: Run focused frontend tests**

```bash
cd frontend && npm test -- --run src/hooks/useAgentActivity.test.ts src/hooks/useAgentActivityViewModel.test.ts src/components/agent-activity/ActivityTopology.test.tsx src/components/agent-activity/CurrentFlowBoard.test.tsx src/components/agent-activity/ContinuityTimeline.test.tsx src/pages/agent-activity/index.test.tsx
```

Expected: all focused tests pass.

- [ ] **Step 6: Commit page integration**

```bash
git add frontend/src/pages/agent-activity/index.tsx frontend/src/pages/agent-activity/index.test.tsx DESIGN.md
git commit -m "Agent Activity: integrate operational views"
```

---

### Task 7: Verify, visually inspect, and prepare worktree integration

**Files:**
- Modify only if verification exposes a defect in files already listed above.

**Interfaces:**
- Consumes: completed feature and existing development scripts.
- Produces: evidence that the worktree is safe to merge into `develop` and a running development stack for user testing.

- [ ] **Step 1: Run all frontend tests**

```bash
cd frontend && npm test -- --run
```

Expected: every Vitest file passes.

- [ ] **Step 2: Run the production frontend build**

```bash
cd frontend && npm run build
```

Expected: TypeScript and Vite finish successfully; existing chunk-size warnings may remain non-blocking.

- [ ] **Step 3: Run backend tests and Ruff**

```bash
cd backend && .venv/bin/pytest
cd backend && /root/project/forgehub/backend/.venv/bin/ruff check app
```

Expected: the full backend suite passes and Ruff reports no findings.

- [ ] **Step 4: Run the strict premium audit**

```bash
python /root/.codex/plugins/cache/openai-curated-remote/frontend-design-premium/1.4.0/skills/frontend-design-premium/scripts/audit_project.py . --mode strict --no-write
```

Expected: zero errors and zero unresolved findings.

- [ ] **Step 5: Restart development mode from the feature worktree and inspect the route**

```bash
./dev.sh
```

Open `http://localhost:5172/agent-activity` and verify: registered photos/fallback initials, project and database nodes, solid/dashed relation legend and text list, pointer movement, keyboard movement, Organize reset, flow columns, history lanes, readable widths, EN/PT-BR copy, and reduced-motion behavior.

- [ ] **Step 6: Review the complete diff and commit verification fixes**

```bash
git diff --check
git status --short
```

If verification required a correction, stage only the affected files and use:

```bash
git commit -m "Agent Activity: finish operational views"
```

- [ ] **Step 7: Follow the branch-finishing workflow**

Use `superpowers:requesting-code-review`, `superpowers:verification-before-completion`, and `superpowers:finishing-a-development-branch`. Apply the already stated user choice by merging the completed worktree branch into the primary checkout's `develop`, then restart development mode from the primary checkout and report its test URL.
