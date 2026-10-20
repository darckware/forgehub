# External Agent Profile Health Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Audit and surface the runtime-native identity, personality, memory, tools, heartbeat, and Foundation-link layers for Porthus, Aramis, and Dartan without copying private runtime state or creating fake Hermes profiles.

**Architecture:** Extend the existing safe allow-listed profile-file reader with a runtime-aware health assessment. The backend reports presence, freshness, native entrypoint, knowledge adapter, and actionable issues; it never returns secret files or private memory contents. Agent Activity and the agent detail page consume the same health DTO.

**Tech Stack:** FastAPI, pathlib-safe profile resolver, Pydantic v2, React/TanStack Query/Zod, pytest with temporary directories, Vitest/React Testing Library.

**Spec:** `docs/plans/2026-08-29-agent-activity-continuity-design.md`

## Global Constraints

- Porthus, Aramis, and Dartan remain external runtime agents.
- Private Claude, Codex, and Gemini state remains outside Foundation and is never copied wholesale.
- Required operating layers are equivalent by purpose, not forced into identical filenames.
- Profile health describes presence and provenance; it does not expose credentials, raw memory, history, settings, or secret-bearing files.
- Explicit project governance and Foundation contracts override profile personality.

## File Structure

- Modify `backend/app/core/agent_profile_files.py`: runtime-specific layer contract and pure health evaluator.
- Modify `backend/app/api/schemas/agent.py`: profile health and layer DTOs.
- Modify `backend/app/api/routes/agent.py`: `GET /api/v1/agents/{agent_id}/profile-health`.
- Modify `backend/app/tests/test_agent_profile_files.py`: runtime mapping, missing/stale layers, and path-safety tests.
- Modify `backend/app/core/agent_activity.py`: attach safe health summary to agent nodes.
- Modify `frontend/src/hooks/useAgent.ts`: health schemas and query.
- Modify `frontend/src/components/AgentProfileFileChips.tsx`: layer status and provenance.
- Create `frontend/src/components/agent-activity/ProfileHealthSummary.tsx`: compact inspector presentation.
- Modify `frontend/src/components/agent-activity/AgentInspector.tsx`: display health without private content.
- Modify `frontend/src/i18n/locales/{pt-BR,en}/agent.json` and `agentActivity.json`: health copy.
- Create `frontend/src/components/agent-activity/ProfileHealthSummary.test.tsx`: accessible status coverage.

---

### Task 1: Define runtime-aware profile layers

**Files:**
- Modify: `backend/app/core/agent_profile_files.py`
- Modify: `backend/app/tests/test_agent_profile_files.py`

**Interfaces:**
- Produces: `ProfileLayerRequirement`, `ProfileLayerHealth`, `required_profile_layers(runtime_type)`, and `evaluate_profile_health(home_dir, host_home, runtime_type, profile_slug, now)`.
- Consumes only allow-listed profile Markdown plus explicitly known adapter paths; no directory-wide content scan.

- [ ] **Step 1: Write failing runtime mapping tests**

```python
def test_external_runtime_profile_layers_use_native_entrypoints():
    assert required_profile_layers("claude")["entrypoint"].accepted_files == ("CLAUDE.md",)
    assert required_profile_layers("codex")["entrypoint"].accepted_files == ("AGENTS.md",)
    assert required_profile_layers("agy")["entrypoint"].required is False

def test_all_external_runtimes_require_operating_character_and_heartbeat():
    for runtime in ("claude", "codex", "agy"):
        layers = required_profile_layers(runtime)
        assert layers["identity"].accepted_files == ("IDENTITY.md",)
        assert layers["personality"].accepted_files == ("SOUL.md",)
        assert layers["heartbeat"].accepted_files == ("HEARTBEAT.md",)
```

- [ ] **Step 2: Run and verify failure**

Run: `cd backend && .venv/bin/pytest app/tests/test_agent_profile_files.py -k profile_layers -v`

Expected: FAIL because the layer contract does not exist.

- [ ] **Step 3: Implement the layer contract**

```python
@dataclass(frozen=True)
class ProfileLayerRequirement:
    key: str
    accepted_files: tuple[str, ...]
    required: bool = True

COMMON_LAYERS = {
    "identity": ProfileLayerRequirement("identity", ("IDENTITY.md",)),
    "personality": ProfileLayerRequirement("personality", ("SOUL.md",)),
    "operator": ProfileLayerRequirement("operator", ("USER.md",)),
    "tools": ProfileLayerRequirement("tools", ("TOOLS.md",)),
    "memory": ProfileLayerRequirement("memory", ("MEMORY.md",)),
    "heartbeat": ProfileLayerRequirement("heartbeat", ("HEARTBEAT.md",)),
    "foundation": ProfileLayerRequirement("foundation", ("FOUNDATION_LINK.md",)),
}

RUNTIME_ENTRYPOINTS = {
    "claude": ProfileLayerRequirement("entrypoint", ("CLAUDE.md",)),
    "codex": ProfileLayerRequirement("entrypoint", ("AGENTS.md",)),
    "agy": ProfileLayerRequirement("entrypoint", (), required=False),
}
```

For Agy, the runtime configuration/hook system is not exposed through the Markdown file endpoint; absence of a Markdown entrypoint is informational, not unhealthy.

- [ ] **Step 4: Add safe evaluation tests**

Create temporary directories containing only representative Markdown. Assert `healthy` when required layers exist, `degraded` with explicit missing-layer keys when one is absent, and `unavailable` when the home cannot resolve. Assert `.env`, `auth.json`, `.credentials.json`, history files, and symlink escapes never appear in layer results.

- [ ] **Step 5: Run core profile tests**

Run: `cd backend && .venv/bin/pytest app/tests/test_agent_profile_files.py -v`

Expected: PASS.

- [ ] **Step 6: Commit the health evaluator**

```bash
git add backend/app/core/agent_profile_files.py backend/app/tests/test_agent_profile_files.py
git commit -m "Agents: assess runtime-native profile health"
```

### Task 2: Expose safe profile health through the Agent API

**Files:**
- Modify: `backend/app/api/schemas/agent.py`
- Modify: `backend/app/api/routes/agent.py`
- Modify: `backend/app/tests/test_agent_profile_files.py`

**Interfaces:**
- Produces: `GET /api/v1/agents/{agent_id}/profile-health -> AgentProfileHealthOut`.
- Response includes agent/runtime/home path, overall status, layer records, issues, and `checked_at`; no file content.

- [ ] **Step 1: Write failing API tests**

```python
response = await client.get(f"/api/v1/agents/{agent_id}/profile-health")
assert response.status_code == 200
body = response.json()
assert body["status"] == "healthy"
assert {layer["key"] for layer in body["layers"]} >= {"identity", "personality", "memory", "heartbeat"}
assert all("content" not in layer for layer in body["layers"])
```

- [ ] **Step 2: Run and verify failure**

Run: `cd backend && .venv/bin/pytest app/tests/test_agent_profile_files.py -k profile_health_api -v`

Expected: FAIL with 404.

- [ ] **Step 3: Add output schemas**

```python
class AgentProfileLayerOut(BaseModel):
    key: str
    status: Literal["healthy", "missing", "stale", "optional"]
    filename: str | None
    path: str | None
    modified_at: datetime | None
    required: bool

class AgentProfileHealthOut(BaseModel):
    agent_id: uuid.UUID
    runtime_type: str | None
    home_path: str | None
    status: Literal["healthy", "degraded", "unavailable"]
    layers: list[AgentProfileLayerOut]
    issues: list[str]
    checked_at: datetime
```

- [ ] **Step 4: Implement the route**

Resolve the agent through the existing ORM query, derive its effective home, call the pure evaluator, and return metadata only. Reuse the existing `resolve_home_dir` and allow-list logic. Return 404 for an unknown agent and `status="unavailable"` rather than 500 for a missing home.

- [ ] **Step 5: Run API tests**

Run: `cd backend && .venv/bin/pytest app/tests/test_agent_profile_files.py -v`

Expected: PASS.

- [ ] **Step 6: Commit the API**

```bash
git add backend/app/api/schemas/agent.py backend/app/api/routes/agent.py backend/app/tests/test_agent_profile_files.py
git commit -m "Agents: expose profile health"
```

### Task 3: Audit the installed Porthus, Aramis, and Dartan structures

**Files:**
- Modify only when a required layer is verifiably absent: runtime-native files under `/root/.claude`, `/root/.codex`, or `/root/.gemini/config` through the separately authorized operational workflow.
- Publish: redacted audit candidate through `/root/.codex/hooks/knowledge_cycle.py` after verification.

**Interfaces:**
- Consumes the profile-health endpoint and canonical Foundation contracts `PORTHUS.md`, `ARAMIS.md`, and `DARTAN.md`.
- Produces an evidence-backed audit; repository code must not fabricate profile contents.

- [ ] **Step 1: Run the read-only health audit**

Query the three registered agent IDs, call each profile-health endpoint, and compare only missing layer keys and canonical paths. Expected native entrypoints: Porthus `CLAUDE.md`, Aramis `AGENTS.md`, Dartan no required Markdown entrypoint.

- [ ] **Step 2: Verify canonical common layers**

Require `IDENTITY.md`, `SOUL.md`, `USER.md`, `TOOLS.md`, `MEMORY.md`, `HEARTBEAT.md`, and `FOUNDATION_LINK.md` for all three. Do not open `.env`, credentials, auth, history, or private database files.

- [ ] **Step 3: Repair only verified missing required layers**

If a required layer is missing, derive its mission and boundary statements from the corresponding Foundation contract. Preserve runtime-native precedence and state explicitly that the file defines character/context, not authority. Use the runtime's accepted instruction surface; do not create `/root/.hermes/profiles/{porthus,aramis,dartan}`.

- [ ] **Step 4: Run native health checks**

For Aramis, run `/usr/bin/python3 /root/.codex/hooks/aramis_memory.py self-test` and `health`. For Porthus and Dartan, run their documented native adapter self-tests from the corresponding Foundation adapter contracts. Report degraded memory without blocking repository work.

- [ ] **Step 5: Re-run the API audit and publish a redacted candidate**

All three must return `healthy` or a documented optional-layer warning. Publish only verified paths, statuses, and repair decisions; never publish file contents, credentials, or raw conversations.

### Task 4: Surface profile health in agent detail and Agent Activity

**Files:**
- Modify: `backend/app/core/agent_activity.py`
- Modify: `backend/app/tests/test_agent_activity.py`
- Modify: `frontend/src/hooks/useAgent.ts`
- Modify: `frontend/src/components/AgentProfileFileChips.tsx`
- Create: `frontend/src/components/agent-activity/ProfileHealthSummary.tsx`
- Create: `frontend/src/components/agent-activity/ProfileHealthSummary.test.tsx`
- Modify: `frontend/src/components/agent-activity/AgentInspector.tsx`
- Modify: `frontend/src/i18n/locales/pt-BR/agent.json`
- Modify: `frontend/src/i18n/locales/en/agent.json`
- Modify: `frontend/src/i18n/locales/pt-BR/agentActivity.json`
- Modify: `frontend/src/i18n/locales/en/agentActivity.json`

**Interfaces:**
- Produces: `useAgentProfileHealth(agentId)`, compact `profile_health` on activity agents, and accessible per-layer status UI.

- [ ] **Step 1: Write failing component tests**

```typescript
it("shows a degraded profile without exposing private contents", () => {
  render(<ProfileHealthSummary health={DEGRADED_HEALTH} />);
  expect(screen.getByText(/Perfil degradado/i)).toBeVisible();
  expect(screen.getByText(/HEARTBEAT.md ausente/i)).toBeVisible();
  expect(screen.queryByText(/credentials|auth\.json|history/i)).not.toBeInTheDocument();
});
```

- [ ] **Step 2: Run and verify failure**

Run: `cd frontend && npm test -- --run src/components/agent-activity/ProfileHealthSummary.test.tsx`

Expected: FAIL because the component is absent.

- [ ] **Step 3: Add schemas, query, and UI**

Parse the API with Zod. Render overall status with icon and text, then required layers with filename/path/freshness. Link existing files to the agent detail profile-file section. Do not render file content in Agent Activity.

- [ ] **Step 4: Attach the safe summary to the activity read model**

Compute only `status`, missing layer keys, and `checked_at` in the activity aggregate. The detailed route remains the source for per-layer metadata. Treat a filesystem lookup failure as a visible degraded source, not as an empty healthy profile.

- [ ] **Step 5: Run focused and full tests**

Run: `cd backend && .venv/bin/pytest app/tests/test_agent_profile_files.py app/tests/test_agent_activity.py -v`

Run: `cd frontend && npm test -- --run src/components/agent-activity/ProfileHealthSummary.test.tsx src/pages/agent-activity/index.test.tsx`

Expected: PASS.

- [ ] **Step 6: Commit UI integration**

```bash
git add backend/app/core/agent_activity.py backend/app/tests/test_agent_activity.py frontend/src/hooks/useAgent.ts frontend/src/components/AgentProfileFileChips.tsx frontend/src/components/agent-activity/ProfileHealthSummary.tsx frontend/src/components/agent-activity/ProfileHealthSummary.test.tsx frontend/src/components/agent-activity/AgentInspector.tsx frontend/src/i18n/locales
git commit -m "Agent Activity: surface profile health"
```

### Task 5: Full verification

**Files:**
- No new production files.

**Interfaces:**
- Produces verified external-agent operating-layer health without secret exposure.

- [ ] **Step 1: Run backend security and regression tests**

Run: `cd backend && .venv/bin/pytest app/tests/test_agent_profile_files.py app/tests/test_agent_activity.py -v`

Run: `cd backend && .venv/bin/ruff check app`

Expected: PASS.

- [ ] **Step 2: Run full application verification**

Run: `cd backend && .venv/bin/pytest`

Run: `cd frontend && npm test && npm run build`

Expected: PASS.

- [ ] **Step 3: Browser-smoke profile health**

Open Porthus, Aramis, and Dartan in Agent Activity and agent detail. Verify runtime-native filenames, status text, canonical paths, and missing-layer behavior. Confirm no secret filenames or contents appear in API responses, DOM text, browser network payloads, or logs.
