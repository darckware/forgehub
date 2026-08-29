# Agent Activity Read Model and UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the current Messages-only activity board with the approved continuity-first operational topology, incident rail, selected-agent inspector, and canonical event timeline.

**Architecture:** Add one read-only backend aggregation route over existing Messages, projects/tasks, executions, checkpoints, approvals, notifications, and ForgeRouter telemetry. Keep domain ownership in the existing tables and expose source freshness and canonical links in a typed response. Replace the current frontend view model with a TanStack Query hook and focused presentational components based on the selected Superdesign draft.

**Tech Stack:** FastAPI, SQLAlchemy async, Pydantic v2, PostgreSQL, React 18, TypeScript, TanStack Query, Zod, Tailwind CSS, Framer Motion, Vitest/React Testing Library, pytest/httpx.

**Spec:** `docs/plans/2026-08-29-agent-activity-continuity-design.md`

## Global Constraints

- Canonical records are authoritative; decorative animation is not state.
- Do not create a parallel Messages, Notifications, Governance, Checkpoint, or execution workflow.
- Motion only represents real dispatched messages and confirmed state transitions and must respect `prefers-reduced-motion`.
- One monitoring request is recorded in Messages and mirrored in Notifications; UI clicks are not standalone decisions.
- External agents remain runtime-native agents, not fake Hermes profiles.
- Keep API calls centralized through `frontend/src/lib/api.ts` and domain hooks.
- Use pt-BR and English i18n keys; do not hardcode operational copy in components.

## File Structure

- Create `backend/app/api/schemas/agent_activity.py`: complete response/request contracts for the activity read model and Athos monitoring command.
- Create `backend/app/core/agent_activity.py`: bounded SQL aggregation, incident derivation, freshness calculation, and canonical-link construction.
- Create `backend/app/api/routes/agent_activity.py`: authenticated read and monitoring endpoints.
- Modify `backend/app/main.py`: register the activity router.
- Create `backend/app/tests/test_agent_activity.py`: integration coverage and cleanup for all aggregated domains.
- Create `frontend/src/hooks/useAgentActivity.ts`: Zod schemas, query, filters, and monitoring mutation.
- Replace `frontend/src/hooks/useAgentActivityViewModel.ts`: map typed API data to geometry only; remove domain-state inference from free text.
- Create `frontend/src/components/agent-activity/ActivityTopology.tsx`: accessible agent nodes and real message edges.
- Create `frontend/src/components/agent-activity/SeverityInbox.tsx`: ordered incidents and Athos action.
- Create `frontend/src/components/agent-activity/AgentInspector.tsx`: selected-agent operational detail.
- Create `frontend/src/components/agent-activity/ContinuityTimeline.tsx`: canonical event timeline.
- Create `frontend/src/components/agent-activity/RequestAthosDialog.tsx`: confirmation and mutation feedback.
- Replace `frontend/src/pages/agent-activity/index.tsx`: four-region responsive composition.
- Modify `frontend/src/i18n/locales/{pt-BR,en}/agentActivity.json`: all labels, errors, empty states, and actions.
- Create `frontend/src/pages/agent-activity/index.test.tsx`: page interaction, accessibility, partial degradation, and monitoring tests.

---

### Task 1: Define the versioned operational read-model contract

**Files:**
- Create: `backend/app/api/schemas/agent_activity.py`
- Test: `backend/app/tests/test_agent_activity.py`

**Interfaces:**
- Produces: `AgentActivityOut`, `ActivityAgentOut`, `ActivityMessageEdgeOut`, `ActivityIncidentOut`, `ActivityTimelineEventOut`, `ActivitySourceFreshnessOut`, `RequestAthosMonitoringIn`, and `RequestAthosMonitoringOut`.
- Consumes: UUIDs and timestamps from existing domain models; no ORM object crosses the API boundary.

- [ ] **Step 1: Write the failing schema test**

```python
def test_agent_activity_contract_rejects_incident_without_source_id():
    from pydantic import ValidationError
    from app.api.schemas.agent_activity import ActivityIncidentOut

    with pytest.raises(ValidationError):
        ActivityIncidentOut(
            key="execution_failed:missing",
            kind="execution_failed",
            severity="error",
            title="Execution failed",
            occurred_at=datetime.now(timezone.utc),
            source_type="task_execution",
            source_id=None,
            affected_agent_id=None,
            project_id=None,
            task_id=None,
            execution_id=None,
            checkpoint_id=None,
            resume_from_step_key=None,
            error_code="EXEC_RUNTIME_502",
            blocker_code=None,
            summary="Runner stopped",
            recommended_action="request_athos_monitoring",
            prior_attempts=[],
        )
```

- [ ] **Step 2: Run the test and verify the module is missing**

Run: `cd backend && .venv/bin/pytest app/tests/test_agent_activity.py::test_agent_activity_contract_rejects_incident_without_source_id -v`

Expected: FAIL with `ModuleNotFoundError: app.api.schemas.agent_activity`.

- [ ] **Step 3: Implement the Pydantic contracts**

```python
class ActivityIncidentOut(BaseModel):
    key: str
    kind: Literal["execution_failed", "heartbeat_lost", "runtime_limit", "blocked", "approval_pending", "source_unavailable"]
    severity: Literal["info", "warning", "error", "critical"]
    title: str
    occurred_at: datetime
    source_type: str
    source_id: uuid.UUID
    affected_agent_id: uuid.UUID | None = None
    project_id: uuid.UUID | None = None
    task_id: uuid.UUID | None = None
    execution_id: uuid.UUID | None = None
    checkpoint_id: uuid.UUID | None = None
    resume_from_step_key: str | None = None
    error_code: str | None = None
    blocker_code: str | None = None
    summary: str | None = None
    recommended_action: Literal["request_athos_monitoring", "open_approval", "open_message", "inspect_execution"]
    prior_attempts: list[dict[str, Any]] = Field(default_factory=list)

class AgentActivityOut(BaseModel):
    generated_at: datetime
    project_id: uuid.UUID | None
    agents: list[ActivityAgentOut]
    message_edges: list[ActivityMessageEdgeOut]
    incidents: list[ActivityIncidentOut]
    timeline: list[ActivityTimelineEventOut]
    source_freshness: list[ActivitySourceFreshnessOut]
```

Define every nested field explicitly, including canonical record paths such as `/demands?message=<uuid>`, `/tasks/<uuid>`, and `/governance/<uuid>`.

- [ ] **Step 4: Run the schema tests**

Run: `cd backend && .venv/bin/pytest app/tests/test_agent_activity.py -k contract -v`

Expected: PASS.

- [ ] **Step 5: Commit the contract**

```bash
git add backend/app/api/schemas/agent_activity.py backend/app/tests/test_agent_activity.py
git commit -m "Agent Activity: define operational read model"
```

### Task 2: Aggregate canonical state without parsing message prose

**Files:**
- Create: `backend/app/core/agent_activity.py`
- Modify: `backend/app/tests/test_agent_activity.py`

**Interfaces:**
- Consumes: `AgentDemand`, `Agent`, `Project`, `ProjectTask`, `TaskAssignment`, `TaskExecution`, `ExecutionWorkPackage`, `ExecutionLease`, `ProgressCheckpoint`, `ApprovalRequest`, and `Notification`.
- Produces: `async def build_agent_activity(db: AsyncSession, *, project_id: UUID | None, window_minutes: int) -> AgentActivityOut`, `def classify_runtime_failure(error: str | None) -> tuple[str, str | None]`, `build_activity_agents(*, agents, tasks_by_id, executions, checkpoints_by_execution, forgerouter_state) -> list[ActivityAgentOut]`, `build_message_edges(*, demands, agents) -> list[ActivityMessageEdgeOut]`, `build_incidents(*, demands, executions, checkpoints_by_execution, approvals, forgerouter_state) -> list[ActivityIncidentOut]`, and `build_timeline(*, demands, executions, checkpoints_by_execution, approvals, notifications) -> list[ActivityTimelineEventOut]`.

- [ ] **Step 1: Write a failing integration test with one request, failure, checkpoint, and approval**

```python
@pytest.mark.asyncio
async def test_build_activity_joins_message_execution_checkpoint_and_approval(activity_world):
    async with AsyncSessionLocal() as db:
        view = await build_agent_activity(db, project_id=activity_world.project_id, window_minutes=60)

    agent = next(item for item in view.agents if item.id == activity_world.agent_id)
    assert agent.current_execution_id == activity_world.execution_id
    assert agent.latest_checkpoint.resume_from_step_key == "verify-tests"
    assert any(edge.message_id == activity_world.demand_id for edge in view.message_edges)
    incident = next(item for item in view.incidents if item.execution_id == activity_world.execution_id)
    assert incident.error_code == "EXEC_RUNTIME_502"
    assert incident.checkpoint_id == activity_world.checkpoint_id
    assert any(event.source_id == activity_world.approval_id for event in view.timeline)
```

- [ ] **Step 2: Run the focused test and verify failure**

Run: `cd backend && .venv/bin/pytest app/tests/test_agent_activity.py::test_build_activity_joins_message_execution_checkpoint_and_approval -v`

Expected: FAIL because `build_agent_activity` is undefined.

- [ ] **Step 3: Implement bounded queries and deterministic derivation**

Use `generated_at - timedelta(minutes=window_minutes)` as the lower bound. Query each domain once, index rows by UUID, and build DTOs in memory. Resolve message edges only through `from_agent_id`, `target_agent_id`, and `reply_to_id`; never infer sender/recipient from `body`.

```python
async def build_agent_activity(db, *, project_id, window_minutes):
    generated_at = datetime.now(timezone.utc)
    since = generated_at - timedelta(minutes=window_minutes)
    demands = list((await db.execute(
        select(AgentDemand).where(
            AgentDemand.updated_at >= since,
            *([AgentDemand.project_id == project_id] if project_id else []),
        ).order_by(AgentDemand.updated_at.desc()).limit(500)
    )).scalars())
    agents, tasks_by_id, executions, checkpoints_by_execution = await _load_execution_context(
        db, project_id=project_id, since=since
    )
    approvals, notifications = await _load_attention_context(
        db, project_id=project_id, since=since
    )
    forgerouter_state, forgerouter_freshness = await _load_forgerouter_state()
    return AgentActivityOut(
        generated_at=generated_at,
        project_id=project_id,
        agents=build_activity_agents(
            agents=agents,
            tasks_by_id=tasks_by_id,
            executions=executions,
            checkpoints_by_execution=checkpoints_by_execution,
            forgerouter_state=forgerouter_state,
        ),
        message_edges=build_message_edges(demands=demands, agents=agents),
        incidents=build_incidents(
            demands=demands,
            executions=executions,
            checkpoints_by_execution=checkpoints_by_execution,
            approvals=approvals,
            forgerouter_state=forgerouter_state,
        ),
        timeline=build_timeline(
            demands=demands,
            executions=executions,
            checkpoints_by_execution=checkpoints_by_execution,
            approvals=approvals,
            notifications=notifications,
        ),
        source_freshness=[
            ActivitySourceFreshnessOut(name="postgres", status="fresh", checked_at=generated_at),
            forgerouter_freshness,
        ],
    )
```

`classify_runtime_failure` maps case-folded evidence containing `quota`, `rate limit`, or `usage limit` to `("runtime_limit", "RUNTIME_LIMIT")`; other dispatch failures remain `("execution_failed", existing_error_code)`.

- [ ] **Step 4: Add partial-source freshness coverage**

Monkeypatch the optional ForgeRouter fetch to raise `httpx.ConnectError`, then assert the response still contains durable DB state and `source_freshness[name="forgerouter"].status == "unavailable"`.

- [ ] **Step 5: Run aggregation tests**

Run: `cd backend && .venv/bin/pytest app/tests/test_agent_activity.py -k 'build_activity or partial_source' -v`

Expected: PASS.

- [ ] **Step 6: Commit the aggregator**

```bash
git add backend/app/core/agent_activity.py backend/app/tests/test_agent_activity.py
git commit -m "Agent Activity: aggregate canonical operations"
```

### Task 3: Expose activity and create idempotent Athos monitoring requests

**Files:**
- Create: `backend/app/api/routes/agent_activity.py`
- Modify: `backend/app/main.py`
- Modify: `backend/app/tests/test_agent_activity.py`

**Interfaces:**
- Produces: `GET /api/v1/agent-activity`, `POST /api/v1/agent-activity/incidents/{incident_key}:request-athos-monitoring`.
- Monitoring returns: `{message_id, message_number, notification_id, created}`.

- [ ] **Step 1: Write failing endpoint and idempotency tests**

```python
first = await client.post(
    f"/api/v1/agent-activity/incidents/{incident_key}:request-athos-monitoring",
    json={"execution_id": str(execution_id), "idempotency_key": key},
)
second = await client.post(
    f"/api/v1/agent-activity/incidents/{incident_key}:request-athos-monitoring",
    json={"execution_id": str(execution_id), "idempotency_key": key},
)
assert first.status_code == second.status_code == 201
assert first.json()["message_id"] == second.json()["message_id"]
assert second.json()["created"] is False
```

- [ ] **Step 2: Run the focused endpoint test**

Run: `cd backend && .venv/bin/pytest app/tests/test_agent_activity.py -k monitoring -v`

Expected: FAIL with 404.

- [ ] **Step 3: Implement the read route and monitoring command**

The GET route requires `demands` view permission through the existing authenticated middleware. For monitoring, resolve Athos by `Agent.profile_slug == "athos"`, resolve the execution/task/project, and call `create_demand_and_notify` with structured identifiers in the body:

```python
payload = DemandSubmitIn(
    from_agent=principal.display_name,
    target_agent_id=athos.id,
    project_id=project_id,
    subject=f"Monitor incident {incident_key}",
    body=json.dumps({
        "contract_version": "forge-agent-incident-monitor/v1",
        "incident_key": incident_key,
        "execution_id": str(execution.id),
        "task_id": str(task.id),
        "requested_by": principal.display_name,
    }, sort_keys=True),
    channel="agent",
    channel_ref=str(execution.id),
    requires_response=True,
)
```

Set `channel_ref = f"agent-activity:{idempotency_key}"` on the demand and use deterministic `Notification.event_key = f"agent-activity:athos-monitor:{idempotency_key}"`. Before creating either record, look up the demand by that exact channel reference and the notification by its event key; return the existing pair on a duplicate request. Do not dispatch work automatically from this action.

- [ ] **Step 4: Register the router and run tests**

Run: `cd backend && .venv/bin/pytest app/tests/test_agent_activity.py -v`

Expected: PASS, including unauthorized/unknown incident/unknown Athos cases.

- [ ] **Step 5: Commit the routes**

```bash
git add backend/app/api/routes/agent_activity.py backend/app/main.py backend/app/tests/test_agent_activity.py
git commit -m "Agent Activity: request Athos monitoring"
```

### Task 4: Add the typed frontend data layer and geometry-only view model

**Files:**
- Create: `frontend/src/hooks/useAgentActivity.ts`
- Replace: `frontend/src/hooks/useAgentActivityViewModel.ts`
- Create: `frontend/src/hooks/useAgentActivity.test.ts`

**Interfaces:**
- Produces: `useAgentActivity(filters)`, `useRequestAthosMonitoring()`, `layoutActivityNodes(agents)`, and exported Zod-derived types.
- Consumes: backend `AgentActivityOut` exactly; no domain inference from subject/body strings.

- [ ] **Step 1: Write failing Zod and layout tests**

```typescript
it("rejects an incident without a canonical source id", () => {
  expect(() => activityIncidentSchema.parse({ ...INCIDENT, source_id: null })).toThrow();
});

it("keeps selected node geometry deterministic", () => {
  expect(layoutActivityNodes(AGENTS)).toEqual(layoutActivityNodes(AGENTS));
});
```

- [ ] **Step 2: Run and verify failure**

Run: `cd frontend && npm test -- --run src/hooks/useAgentActivity.test.ts`

Expected: FAIL because the module does not exist.

- [ ] **Step 3: Implement schemas and hooks**

```typescript
export function useAgentActivity(filters: ActivityFilters) {
  return useQuery({
    queryKey: ["agent-activity", filters],
    queryFn: () => apiClient.get("/api/v1/agent-activity", { params: filters }),
    select: (value) => agentActivitySchema.parse(value),
    refetchInterval: 5_000,
  });
}
```

Keep packet generation keyed by `message_id + dispatch_status + updated_at`. Geometry uses stable agent IDs and separates overlapping positions without changing status.

- [ ] **Step 4: Run frontend hook tests**

Run: `cd frontend && npm test -- --run src/hooks/useAgentActivity.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit the data layer**

```bash
git add frontend/src/hooks/useAgentActivity.ts frontend/src/hooks/useAgentActivityViewModel.ts frontend/src/hooks/useAgentActivity.test.ts
git commit -m "Agent Activity: consume canonical read model"
```

### Task 5: Build the continuity-first page and primary interactions

**Files:**
- Create: `frontend/src/components/agent-activity/ActivityTopology.tsx`
- Create: `frontend/src/components/agent-activity/SeverityInbox.tsx`
- Create: `frontend/src/components/agent-activity/AgentInspector.tsx`
- Create: `frontend/src/components/agent-activity/ContinuityTimeline.tsx`
- Create: `frontend/src/components/agent-activity/RequestAthosDialog.tsx`
- Replace: `frontend/src/pages/agent-activity/index.tsx`
- Modify: `frontend/src/i18n/locales/pt-BR/agentActivity.json`
- Modify: `frontend/src/i18n/locales/en/agentActivity.json`
- Create: `frontend/src/pages/agent-activity/index.test.tsx`

**Interfaces:**
- `ActivityTopology({agents, edges, selectedAgentId, onSelectAgent, onOpenMessage})`.
- `SeverityInbox({incidents, onSelectIncident, onRequestMonitoring})`.
- `AgentInspector({agent, onOpenRecord})`.
- `ContinuityTimeline({events, selectedAgentId})`.
- `RequestAthosDialog({incident, open, onOpenChange})`.

- [ ] **Step 1: Write failing page tests**

```typescript
it("selects an agent and exposes waits, checkpoint, and authorization", async () => {
  renderPage(ACTIVITY_FIXTURE);
  await user.click(screen.getByRole("button", { name: /Dartan/i }));
  expect(screen.getByText(/Resposta de Athos e decisão humana/i)).toBeVisible();
  expect(screen.getByText(/CP-771/i)).toBeVisible();
  expect(screen.getByText(/Transferência de ownership pendente/i)).toBeVisible();
});

it("confirms the exact context before requesting Athos monitoring", async () => {
  renderPage(ACTIVITY_FIXTURE);
  await user.click(screen.getByRole("button", { name: /solicitar monitoramento ao Athos/i }));
  expect(screen.getByRole("dialog")).toHaveTextContent("EXEC_RUNTIME_502");
  expect(screen.getByRole("dialog")).toHaveTextContent("#284");
});
```

- [ ] **Step 2: Run and verify failure**

Run: `cd frontend && npm test -- --run src/pages/agent-activity/index.test.tsx`

Expected: FAIL because the new regions are absent.

- [ ] **Step 3: Implement the selected visual direction**

Follow the selected Superdesign node stored in `.superdesign/resume.json`. Use CSS grid with `minmax(0, 1fr) 22rem` for desktop topology/rail, a full-width lower timeline, and stacked regions below `lg`. Preserve the existing sidebar through `AppLayout`; do not reproduce it inside the page.

Agent nodes are real `<button>` elements. Message edges include an accessible adjacent list or labels linking to Messages. Use `motion-safe:` animation utilities and `useReducedMotion()` for packets.

- [ ] **Step 4: Implement error/empty/stale/partial-source states and i18n**

Use distinct messages for: no active work, API request failed, one optional source unavailable, stale source, monitoring mutation failed, and monitoring request created. Keep the topology height reserved in every state.

- [ ] **Step 5: Run page and full frontend tests**

Run: `cd frontend && npm test -- --run src/pages/agent-activity/index.test.tsx`

Expected: PASS.

Run: `cd frontend && npm test`

Expected: all tests PASS.

- [ ] **Step 6: Build and commit**

Run: `cd frontend && npm run build`

Expected: exit 0 with no TypeScript error.

```bash
git add frontend/src/components/agent-activity frontend/src/pages/agent-activity frontend/src/i18n/locales/pt-BR/agentActivity.json frontend/src/i18n/locales/en/agentActivity.json
git commit -m "Agent Activity: build continuity operations view"
```

### Task 6: End-to-end verification and documentation alignment

**Files:**
- Modify: `docs/plans/2026-08-29-agent-activity-continuity-design.md` only if implementation discovers a verified contract clarification.

**Interfaces:**
- Consumes all earlier tasks.
- Produces a deployable read-only Agent Activity feature with idempotent Athos monitoring.

- [ ] **Step 1: Run backend feature tests and lint**

Run: `cd backend && .venv/bin/pytest app/tests/test_agent_activity.py -v`

Run: `cd backend && .venv/bin/ruff check app`

Expected: PASS.

- [ ] **Step 2: Run full backend and frontend verification**

Run: `cd backend && .venv/bin/pytest`

Run: `cd frontend && npm test && npm run build`

Expected: PASS; existing non-failing bundle-size warnings may remain documented.

- [ ] **Step 3: Run authenticated browser smoke coverage**

Verify `/agent-activity` renders the topology, selects Dartan, opens the monitoring confirmation, cancels without creating a message, and preserves keyboard focus. Verify a partial ForgeRouter outage leaves durable DB state visible with a source warning.

- [ ] **Step 4: Commit any verified documentation clarification**

```bash
git add docs/plans/2026-08-29-agent-activity-continuity-design.md
git commit -m "Docs: align Agent Activity read model"
```
