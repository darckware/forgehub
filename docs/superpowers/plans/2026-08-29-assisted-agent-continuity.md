# Assisted Agent Continuity Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a governed, human-decided continuity case that preserves an interrupted execution, compares compatible successors, records Marcelo's decision, requires successor revalidation, and only then transfers ownership.

**Architecture:** Extend the governed execution domain with one append-audited `ExecutionHandoff` aggregate rather than a parallel orchestration system. Build its immutable continuity package from the existing work package, execution, checkpoint, Messages, and verification evidence. Athos may propose and monitor; only a human principal authorized for `planning.execution.release` may approve a successor.

**Tech Stack:** FastAPI, SQLAlchemy async, Alembic, PostgreSQL JSONB, Pydantic v2, existing authority/audit/notification infrastructure, React/TanStack Query/Zod, pytest and Vitest.

**Spec:** `docs/plans/2026-08-29-agent-activity-continuity-design.md`

## Global Constraints

- No agent transfer is automatic.
- Preserve the interrupted execution and current assignment until a human decision and successor revalidation succeed.
- Athos cannot approve its own proposal or acquire release authority through this feature.
- Continuity packages exclude credentials, raw private conversations, and unbounded runtime state.
- Every command is idempotent, audited, permission-checked, and represented in Agent Activity, Messages, and Notifications.
- The successor revalidates repository state, changed files, checkpoint evidence, and verification results before ownership changes.

## File Structure

- Modify `backend/app/db/models/execution.py`: `ExecutionHandoff` canonical aggregate and status constraints.
- Create `backend/alembic/versions/a8c41e2f6b90_add_execution_handoffs.py`: company-schema table, indexes, checks, and foreign keys.
- Modify `backend/app/api/schemas/execution.py`: continuity proposal, decision, acknowledgement, completion, and output contracts.
- Create `backend/app/core/continuity.py`: package construction, candidate compatibility, hash, redaction, and transition validation.
- Modify `backend/app/api/routes/execution.py`: continuity commands and query endpoints.
- Modify `backend/app/core/agent_activity.py`: include real continuity cases in agents, incidents, and timeline.
- Create `backend/app/tests/test_execution_continuity.py`: lifecycle, authorization, idempotency, conflicts, and cleanup.
- Modify `frontend/src/hooks/useExecutionRuntime.ts`: continuity query/mutations.
- Modify `frontend/src/hooks/useAgentActivity.ts`: parse continuity DTOs.
- Create `frontend/src/components/agent-activity/ContinuityDecisionDialog.tsx`: candidate comparison and decision confirmation.
- Modify `frontend/src/components/agent-activity/ContinuityTimeline.tsx`: canonical continuity stages and decisions.
- Modify `frontend/src/pages/agent-activity/index.test.tsx`: no-auto-transfer and decision behavior.

---

### Task 1: Persist the governed continuity aggregate

**Files:**
- Modify: `backend/app/db/models/execution.py`
- Create: `backend/alembic/versions/a8c41e2f6b90_add_execution_handoffs.py`
- Test: `backend/app/tests/test_execution_continuity.py`

**Interfaces:**
- Produces: `ExecutionHandoff` with statuses `awaiting_decision`, `approved`, `revalidating`, `completed`, `rejected`, `cancelled`.
- Consumes: interrupted `TaskExecution`, existing/current and selected `TaskAssignment`, selected `AgentRuntimeProfile`, and optional monitoring `AgentDemand`.

- [ ] **Step 1: Write a failing model persistence test**

```python
@pytest.mark.asyncio
async def test_handoff_starts_awaiting_human_decision(continuity_world):
    async with AsyncSessionLocal() as db:
        row = ExecutionHandoff(
            project_id=continuity_world.project_id,
            task_id=continuity_world.task_id,
            interrupted_execution_id=continuity_world.execution_id,
            current_assignment_id=continuity_world.assignment_id,
            proposed_by_type="agent",
            proposed_by_id=continuity_world.athos_id,
            proposed_by_name="Athos",
            reason_code="runtime_limit",
            continuity_package={"contract_version": "forge-continuity-package/v1"},
            continuity_package_hash="0" * 64,
            candidate_options=[],
            status="awaiting_decision",
            idempotency_key=f"handoff-{uuid.uuid4()}",
        )
        db.add(row)
        await db.commit()
        assert row.selected_assignment_id is None
        assert row.decided_at is None
```

- [ ] **Step 2: Run and verify failure**

Run: `cd backend && .venv/bin/pytest app/tests/test_execution_continuity.py::test_handoff_starts_awaiting_human_decision -v`

Expected: FAIL because `ExecutionHandoff` and its table do not exist.

- [ ] **Step 3: Add the model**

```python
HANDOFF_STATUSES = ("awaiting_decision", "approved", "revalidating", "completed", "rejected", "cancelled")

class ExecutionHandoff(Base, TimestampMixin):
    __tablename__ = "execution_handoffs"
    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    project_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company.projects.id", ondelete="CASCADE"), nullable=False)
    task_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company.project_tasks.id", ondelete="CASCADE"), nullable=False)
    interrupted_execution_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("company.task_executions.id", ondelete="RESTRICT"), nullable=False)
    current_assignment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("company.task_assignments.id", ondelete="SET NULL"))
    selected_assignment_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("company.task_assignments.id", ondelete="SET NULL"))
    selected_runtime_profile_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("company.agent_runtime_profiles.id", ondelete="SET NULL"))
    resumed_execution_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("company.task_executions.id", ondelete="SET NULL"))
    monitoring_demand_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("company.agent_demands.id", ondelete="SET NULL"))
    proposed_by_type: Mapped[str] = mapped_column(String(20), nullable=False)
    proposed_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    proposed_by_name: Mapped[str] = mapped_column(String(150), nullable=False)
    reason_code: Mapped[str] = mapped_column(String(100), nullable=False)
    continuity_package: Mapped[dict] = mapped_column(JSONB, nullable=False)
    continuity_package_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    candidate_options: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    status: Mapped[str] = mapped_column(String(30), nullable=False, default="awaiting_decision")
    decided_by_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True))
    decided_by_name: Mapped[str | None] = mapped_column(String(150))
    decision_comment: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    idempotency_key: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
```

Add a partial unique index preventing more than one handoff in `awaiting_decision`, `approved`, or `revalidating` for the same interrupted execution.

- [ ] **Step 4: Write the Alembic migration with exact company-schema constraints**

Use `down_revision = "d4b7e91a2c63"`. Create `company.execution_handoffs`, named foreign keys, `ck_execution_handoff_status`, the idempotency unique constraint, and the partial active-case index. Downgrade drops the index then table.

- [ ] **Step 5: Apply and test migration**

Run: `cd backend && .venv/bin/alembic upgrade head && .venv/bin/alembic current`

Expected: `a8c41e2f6b90 (head)`.

Run: `cd backend && .venv/bin/pytest app/tests/test_execution_continuity.py::test_handoff_starts_awaiting_human_decision -v`

Expected: PASS.

- [ ] **Step 6: Commit persistence**

```bash
git add backend/app/db/models/execution.py backend/alembic/versions/a8c41e2f6b90_add_execution_handoffs.py backend/app/tests/test_execution_continuity.py
git commit -m "Execution: persist assisted handoffs"
```

### Task 2: Build and validate the redacted continuity package

**Files:**
- Create: `backend/app/core/continuity.py`
- Modify: `backend/app/tests/test_execution_continuity.py`

**Interfaces:**
- Produces: `async def build_continuity_package(db, execution_id) -> dict`, `async def compatible_candidates(db, execution_id) -> list[dict]`, `def continuity_hash(payload) -> str`, and `validate_transition(current, requested)`.
- Consumes: issued work package payload, task/assignment/project, latest checkpoint/evidence, bounded related Messages, runtime profiles, memberships, and runner capabilities.

- [ ] **Step 1: Write failing package and redaction tests**

```python
package = await build_continuity_package(db, continuity_world.execution_id)
assert package["contract_version"] == "forge-continuity-package/v1"
assert package["checkpoint"]["resume_from_step_key"] == "verify-tests"
assert package["verification"]["commands"] == ["npm test"]
serialized = json.dumps(package).lower()
assert "api_key" not in serialized
assert "authorization: bearer" not in serialized
```

- [ ] **Step 2: Run and verify failure**

Run: `cd backend && .venv/bin/pytest app/tests/test_execution_continuity.py -k package -v`

Expected: FAIL because the continuity core does not exist.

- [ ] **Step 3: Implement package construction**

The returned dictionary must contain exactly these top-level keys: `contract_version`, `objective`, `scope`, `repository`, `task`, `execution`, `work_package`, `changed_files`, `checkpoint`, `verification`, `messages`, `blockers`, `constraints`, and `provenance`.

Read changed files only from structured checkpoint `state_snapshot.changed_files` or execution-result artifacts. Do not run Git from the API request and do not parse prose for paths. Limit related Messages to 100 rows linked by project/task/execution and emit identifiers plus bounded summaries, never attachments or secret fields.

- [ ] **Step 4: Implement deterministic candidate ranking**

Filter to active project memberships and active runtime profiles whose runtime appears in membership `allowed_runtimes` and runner capabilities. Exclude the current assignment. Score: +40 runtime online, +25 purpose `implementation`, +20 allowed runtime, +10 allocation below 100%, +5 `can_review`; subtract 30 when the candidate has reached its concurrency limit. Return the score and individual reasons so the UI can explain the recommendation.

- [ ] **Step 5: Run core tests**

Run: `cd backend && .venv/bin/pytest app/tests/test_execution_continuity.py -k 'package or candidate or transition' -v`

Expected: PASS.

- [ ] **Step 6: Commit core continuity logic**

```bash
git add backend/app/core/continuity.py backend/app/tests/test_execution_continuity.py
git commit -m "Execution: build continuity packages"
```

### Task 3: Add proposal and human decision commands

**Files:**
- Modify: `backend/app/api/schemas/execution.py`
- Modify: `backend/app/api/routes/execution.py`
- Modify: `backend/app/tests/test_execution_continuity.py`

**Interfaces:**
- Produces: `POST /api/v1/executions/{execution_id}/continuity-cases`, `GET /api/v1/continuity-cases/{case_id}`, and `POST /api/v1/continuity-cases/{case_id}:decide`.
- Proposal body: `{reason_code, monitoring_demand_id?, idempotency_key}`.
- Decision body: `{decision: "approve"|"reject", selected_assignment_id?, selected_runtime_profile_id?, comment?, idempotency_key}`.

- [ ] **Step 1: Write failing lifecycle and authority tests**

```python
proposed = await athos.post(f"/api/v1/executions/{execution_id}/continuity-cases", json=proposal)
assert proposed.status_code == 201
assert proposed.json()["status"] == "awaiting_decision"
assert proposed.json()["selected_assignment_id"] is None

denied = await athos.post(f"/api/v1/continuity-cases/{case_id}:decide", json=decision)
assert denied.status_code == 403

approved = await admin.post(f"/api/v1/continuity-cases/{case_id}:decide", json=decision)
assert approved.status_code == 200
assert approved.json()["status"] == "approved"
```

- [ ] **Step 2: Run and verify failure**

Run: `cd backend && .venv/bin/pytest app/tests/test_execution_continuity.py -k 'proposal or human_decision' -v`

Expected: FAIL with 404.

- [ ] **Step 3: Implement proposal**

Require `planning.execution.manage`. Require the latest checkpoint type to be one of `blocked`, `failed`, `paused`, `heartbeat_lost`, or `reconciled`. Build and hash the package and candidates inside the transaction. Write `AuditEvent(event_type="execution_handoff_proposed")`, a warning Notification, and a Messages record addressed to Marcelo's operator queue or the existing human notification channel. Preserve the execution and assignment unchanged.

- [ ] **Step 4: Implement human-only decision**

Require `principal.principal_type == "user"` before `await authorize_action(db, principal, "planning.execution.release", project_id=handoff.project_id)`. Approval requires selected assignment/profile to appear together in `candidate_options`; rejection requires neither. Store the decision, audit it, and notify all three surfaces. Do not create the successor execution yet.

- [ ] **Step 5: Run endpoint tests**

Run: `cd backend && .venv/bin/pytest app/tests/test_execution_continuity.py -k 'proposal or decision or idempotency' -v`

Expected: PASS, including duplicate keys, invalid candidate, self-approval, and concurrent-case conflicts.

- [ ] **Step 6: Commit commands**

```bash
git add backend/app/api/schemas/execution.py backend/app/api/routes/execution.py backend/app/tests/test_execution_continuity.py
git commit -m "Execution: govern continuity decisions"
```

### Task 4: Require successor acknowledgement and revalidation before transfer

**Files:**
- Modify: `backend/app/api/schemas/execution.py`
- Modify: `backend/app/api/routes/execution.py`
- Modify: `backend/app/tests/test_execution_continuity.py`

**Interfaces:**
- Produces: `POST /api/v1/continuity-cases/{case_id}:acknowledge` and `POST /api/v1/continuity-cases/{case_id}:complete`.
- Acknowledge body: package hash plus repository/checkpoint/verification evidence.
- Complete body: revalidation result, evidence refs, and idempotency key.

- [ ] **Step 1: Write failing no-transfer-before-revalidation test**

```python
early = await admin.post(f"/api/v1/continuity-cases/{case_id}:complete", json=completion)
assert early.status_code == 409
assert early.json()["detail"] == "Successor must acknowledge the continuity package first"
assert await current_task_assignment(db, task_id) == original_assignment_id
```

- [ ] **Step 2: Run and verify failure**

Run: `cd backend && .venv/bin/pytest app/tests/test_execution_continuity.py -k revalidation -v`

Expected: FAIL because acknowledgement/completion routes are absent.

- [ ] **Step 3: Implement acknowledgement**

Only the selected agent service principal or a human with `planning.execution.manage` may acknowledge. Require the submitted package hash to equal the stored hash. Require structured confirmations for repository path, changed files reviewed, checkpoint reviewed, and verification plan reviewed. Set status `revalidating`, store acknowledgement in the package provenance, audit, and notify.

- [ ] **Step 4: Implement completion and ownership transfer**

If revalidation fails, keep the original assignment current, set the handoff back to `awaiting_decision` with a new incident, and require a new decision. If it succeeds, release the old `TaskAssignment`, activate the selected assignment, create a child `TaskExecution` with `parent_execution_id` and selected runtime/work package, record a `resumed` checkpoint referencing the interrupted execution, then set the handoff `completed`.

- [ ] **Step 5: Run complete lifecycle tests**

Run: `cd backend && .venv/bin/pytest app/tests/test_execution_continuity.py -v`

Expected: PASS and prove the ownership update and child execution occur only after successful revalidation.

- [ ] **Step 6: Commit transfer lifecycle**

```bash
git add backend/app/api/schemas/execution.py backend/app/api/routes/execution.py backend/app/tests/test_execution_continuity.py
git commit -m "Execution: revalidate continuity transfers"
```

### Task 5: Integrate continuity cases into Agent Activity

**Files:**
- Modify: `backend/app/core/agent_activity.py`
- Modify: `backend/app/tests/test_agent_activity.py`
- Modify: `frontend/src/hooks/useExecutionRuntime.ts`
- Modify: `frontend/src/hooks/useAgentActivity.ts`
- Create: `frontend/src/components/agent-activity/ContinuityDecisionDialog.tsx`
- Modify: `frontend/src/components/agent-activity/ContinuityTimeline.tsx`
- Modify: `frontend/src/pages/agent-activity/index.tsx`
- Modify: `frontend/src/pages/agent-activity/index.test.tsx`

**Interfaces:**
- Consumes the continuity case routes and DTOs.
- Produces a candidate comparison dialog and canonical timeline states with one synchronized decision.

- [ ] **Step 1: Write failing UI tests**

```typescript
it("does not offer transfer before Marcelo chooses a candidate", () => {
  renderPage(AWAITING_DECISION_FIXTURE);
  expect(screen.getByText(/Aguardando decisão de Marcelo/i)).toBeVisible();
  expect(screen.queryByRole("button", { name: /iniciar transferência/i })).not.toBeInTheDocument();
});

it("compares candidate capability, availability, runtime, and risk", async () => {
  renderPage(AWAITING_DECISION_FIXTURE);
  await user.click(screen.getByRole("button", { name: /decisão requerida/i }));
  expect(screen.getByRole("dialog")).toHaveTextContent("Aramis");
  expect(screen.getByRole("dialog")).toHaveTextContent("runtime online");
  expect(screen.getByRole("dialog")).toHaveTextContent("risco baixo");
});
```

- [ ] **Step 2: Run and verify failure**

Run: `cd frontend && npm test -- --run src/pages/agent-activity/index.test.tsx`

Expected: FAIL because continuity cases are not rendered.

- [ ] **Step 3: Extend the backend read model and frontend schemas**

Add continuity cases to affected agents, incidents, and timeline using the stored aggregate. Remove any prototype-only inferred handoff state.

- [ ] **Step 4: Implement the decision dialog and mutation states**

Show package hash, interrupted owner, checkpoint, successor score reasons, context-loss risk, and exact consequence. Approval/rejection calls the canonical decision endpoint; on success invalidate `agent-activity`, `notifications`, `demands`, and `continuity-case` query keys.

- [ ] **Step 5: Run integration verification**

Run: `cd backend && .venv/bin/pytest app/tests/test_execution_continuity.py app/tests/test_agent_activity.py -v`

Run: `cd frontend && npm test -- --run src/pages/agent-activity/index.test.tsx`

Expected: PASS.

- [ ] **Step 6: Commit UI integration**

```bash
git add backend/app/core/agent_activity.py backend/app/tests/test_agent_activity.py frontend/src/hooks/useExecutionRuntime.ts frontend/src/hooks/useAgentActivity.ts frontend/src/components/agent-activity/ContinuityDecisionDialog.tsx frontend/src/components/agent-activity/ContinuityTimeline.tsx frontend/src/pages/agent-activity
git commit -m "Agent Activity: govern continuity decisions"
```

### Task 6: Full verification

**Files:**
- No new production files.

**Interfaces:**
- Produces a migration-safe, audited, human-decided continuity lifecycle.

- [ ] **Step 1: Verify migration round trip on a disposable test database**

Run upgrade to `a8c41e2f6b90`, downgrade to `d4b7e91a2c63`, then upgrade to head. Confirm the operational database remains at head afterward.

- [ ] **Step 2: Run backend tests and lint**

Run: `cd backend && .venv/bin/pytest app/tests/test_execution_continuity.py app/tests/test_agent_activity.py -v`

Run: `cd backend && .venv/bin/ruff check app`

Expected: PASS.

- [ ] **Step 3: Run full application verification**

Run: `cd backend && .venv/bin/pytest`

Run: `cd frontend && npm test && npm run build`

Expected: PASS.

- [ ] **Step 4: Browser-smoke the decision gate**

Create an interrupted execution, propose continuity as Athos, verify all three surfaces show one pending decision, approve as Marcelo, verify no assignment changes before acknowledgement, acknowledge/revalidate as the successor, and verify the final owner plus resumed checkpoint.
