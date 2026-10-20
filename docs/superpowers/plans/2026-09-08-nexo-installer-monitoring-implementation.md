# Nexo Installer Distribution and Monitoring Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a secure administrator area that builds reusable Nexo agent binaries, generates a one-time workstation ZIP, and tracks installation through the first authenticated report.

**Architecture:** The host bridge performs only allowlisted Nexo source/build operations and writes versioned artifacts to storage shared with the backend. FastAPI owns build metadata, one-time package materialization, token rotation, state/event history, and report reconciliation; React exposes the catalog, filters, package action, and history without ever receiving a raw token outside the ZIP.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy async, PostgreSQL/Alembic, httpx, React 18, TypeScript, TanStack Query, Tailwind, shadcn/ui, Vitest/RTL, pytest.

**Spec:** `docs/superpowers/specs/2026-09-08-nexo-installer-monitoring-design.md`

## Global Constraints

- Raw device tokens are never logged, stored, returned as JSON, or placed in events.
- Package delivery is one-time: every new download rotates the workstation token.
- A workstation becomes `online` only after its first valid authenticated report for the current generation.
- Supported platforms are exactly `linux` and `windows`, with one immutable binary per Git SHA/platform.
- The browser may send only workstation IDs and supported platform values, never commands, refs, or paths.
- Workstation packages are temporary and deleted after the response; shared versioned binaries remain persistent.
- Build/package/download operations require an administrator.
- UI copy must exist in English, Portuguese, and Spanish and must not communicate state by color alone.
- Remote execution, automatic update, reinstall, uninstall, Darckware linkage, reports/PDF, and raw Headscale policy editing remain out of scope.
- Before UI implementation, read and apply both `frontend-design-premium:frontend-design` and `frontend-design-premium:frontend-design-premium`.

---

## File map

- `backend/app/db/models/nexo_installation.py`: build, current installation, and append-only event persistence.
- `backend/app/api/schemas/nexo_installation.py`: stable API projections and filter/status types.
- `backend/app/core/nexo_builds.py`: backend client for the fixed bridge build contract and artifact verification.
- `backend/app/core/nexo_packages.py`: safe ZIP/config/manifest/script generation.
- `backend/app/api/routes/nexo_installation.py`: admin build/list/detail/package endpoints.
- `host-bridge/nexo_builds.py`: allowlisted source revision and Linux/Windows compiler functions.
- `host-bridge/app.py`: authenticated `/v1/nexo/*` bridge routes only.
- `frontend/src/hooks/useNexoInstallations.ts`: query/mutation contracts and one-time file download.
- `frontend/src/pages/nexo-agents/index.tsx`: primary build and installation monitoring page.
- `frontend/src/pages/nexo-agents/index.test.tsx`: page behavior and accessibility coverage.
- `frontend/src/pages/clients/[id].tsx`: contextual workstation status and actions.
- `frontend/src/i18n/locales/{en,pt-BR,es}/nexoAgents.json`: domain copy.

### Task 1: Persist build and installation history

**Files:**
- Create: `backend/app/db/models/nexo_installation.py`
- Create: `backend/alembic/versions/5a8c1e7d9f20_add_nexo_installation_tracking.py`
- Modify: `backend/app/db/models/__init__.py`
- Test: `backend/app/tests/test_nexo_installation_models.py`

**Interfaces:**
- Produces: `NexoAgentBuild`, `WorkstationInstallation`, `WorkstationInstallationEvent` and the exact status constants used by every later backend task.
- Consumes: `Base`, `TimestampMixin`, `Workstation`, and `User`.

- [ ] **Step 1: Write failing persistence tests**

```python
async def test_one_current_installation_per_workstation(db, workstation):
    build = await ready_build(db, os_kind=workstation.os_kind)
    db.add_all([
        WorkstationInstallation(workstation_id=workstation.id, build_id=build.id, status="package_ready", package_generated_at=utcnow()),
        WorkstationInstallation(workstation_id=workstation.id, build_id=build.id, status="package_ready", package_generated_at=utcnow()),
    ])
    with pytest.raises(IntegrityError):
        await db.commit()

async def test_installation_event_preserves_generation_history(db, installation):
    db.add(WorkstationInstallationEvent(
        installation_id=installation.id,
        event_type="package_generated",
        from_status=None,
        to_status="package_ready",
        detail="linux build abc1234",
    ))
    await db.commit()
    assert (await events_for(db, installation.id))[0].event_type == "package_generated"
```

- [ ] **Step 2: Run the new model tests and confirm missing imports/tables fail**

Run: `cd backend && POSTGRES_HOST=127.0.0.1 .venv/bin/python -m pytest app/tests/test_nexo_installation_models.py -q`

Expected: FAIL because `app.db.models.nexo_installation` does not exist.

- [ ] **Step 3: Add the three focused SQLAlchemy models and constraints**

```python
BUILD_STATUSES = ("queued", "building", "ready", "failed")
INSTALLATION_STATUSES = ("package_ready", "downloaded", "online", "outdated", "error")
INSTALLATION_EVENT_TYPES = ("package_generated", "downloaded", "first_report", "version_mismatch", "error")

class NexoAgentBuild(Base, TimestampMixin):
    __tablename__ = "nexo_agent_builds"
    id = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    git_sha = mapped_column(String(40), nullable=False)
    agent_version = mapped_column(String(50), nullable=False)
    os_kind = mapped_column(String(20), nullable=False)
    status = mapped_column(String(20), nullable=False)
    artifact_path = mapped_column(String(500), nullable=True)
    artifact_size = mapped_column(BigInteger, nullable=True)
    sha256 = mapped_column(String(64), nullable=True)
    build_log_excerpt = mapped_column(String(2000), nullable=True)
    started_at = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at = mapped_column(DateTime(timezone=True), nullable=True)
    __table_args__ = (
        UniqueConstraint("git_sha", "os_kind", name="uq_nexo_agent_builds_sha_os"),
        CheckConstraint("os_kind IN ('linux', 'windows')", name="ck_nexo_agent_builds_os_kind"),
        CheckConstraint("status IN ('queued', 'building', 'ready', 'failed')", name="ck_nexo_agent_builds_status"),
    )
```

Define `WorkstationInstallation.workstation_id` as unique with `ondelete="CASCADE"`, `build_id` with `ondelete="RESTRICT"`, bounded `last_error`, generation/download/online timestamps, and status constraint. Define event FK cascade, nullable actor FK `SET NULL`, bounded detail, transition snapshots, created timestamp, and indexes on installation/time and build status.

- [ ] **Step 4: Add a hand-reviewed company-schema migration**

Create all three tables in `company`, all status/check/unique constraints, and indexes. Set `down_revision` to the actual Alembic head reported immediately before creation; if the repository has multiple heads, create a merge revision first rather than guessing.

- [ ] **Step 5: Apply migration and run focused tests**

Run: `cd backend && POSTGRES_HOST=127.0.0.1 .venv/bin/python -m alembic upgrade head`

Run: `cd backend && POSTGRES_HOST=127.0.0.1 .venv/bin/python -m pytest app/tests/test_nexo_installation_models.py -q`

Expected: migration succeeds and tests PASS.

- [ ] **Step 6: Commit the persistence slice**

```bash
git add backend/app/db/models/nexo_installation.py backend/app/db/models/__init__.py backend/alembic/versions/5a8c1e7d9f20_add_nexo_installation_tracking.py backend/app/tests/test_nexo_installation_models.py
git commit -m "Nexo: track builds and installations"
```

### Task 2: Add the allowlisted host build boundary

**Files:**
- Create: `host-bridge/nexo_builds.py`
- Modify: `host-bridge/app.py`
- Test: `backend/app/tests/test_nexo_host_builds.py`

**Interfaces:**
- Produces: `GET /v1/nexo/source` returning `{git_sha, agent_version}` and `POST /v1/nexo/build/{os_kind}` returning `{git_sha, agent_version, os_kind, artifact_path, artifact_size, sha256, log_excerpt}`.
- Consumes: bridge `X-Bridge-Token`, fixed `NEXO_SOURCE_PATH`, fixed `NEXO_ARTIFACT_ROOT`, and platform path parameter constrained to `linux|windows`.

- [ ] **Step 1: Write failing bridge unit tests around pure functions**

```python
def test_build_command_is_fixed_for_windows(tmp_path):
    command = build_command("windows", "abc123", tmp_path / "agent.exe")
    assert command == ["go", "build", "-trimpath", "-ldflags", "-X main.Version=abc123", "-o", str(tmp_path / "agent.exe"), "./cmd/remote-agent"]
    assert build_environment("windows") == {"GOOS": "windows", "GOARCH": "amd64", "CGO_ENABLED": "0"}

def test_platform_rejects_command_like_input():
    with pytest.raises(ValueError):
        artifact_name("linux;rm -rf /", "abc123")
```

- [ ] **Step 2: Run tests and confirm the module is missing**

Run: `cd backend && .venv/bin/python -m pytest app/tests/test_nexo_host_builds.py -q`

Expected: FAIL importing `host-bridge/nexo_builds.py`.

- [ ] **Step 3: Implement fixed revision and build functions**

Use argument arrays, never `shell=True`. Resolve SHA with `git -C <fixed-source> rev-parse HEAD`; derive version with `git describe --tags --always --dirty` and reject dirty source for a catalog build. Compile in the fixed source directory with a 600-second timeout, write to `<artifact-root>/<sha>/<platform>/nexo-remote-agent[.exe]`, calculate SHA-256 and size, and bound/redact diagnostic output to 2,000 characters.

- [ ] **Step 4: Expose authenticated fixed routes**

```python
@app.get("/v1/nexo/source", response_model=NexoSourceResponse)
async def nexo_source(x_bridge_token: str | None = Header(default=None)):
    _check_token(x_bridge_token)
    return inspect_source()

@app.post("/v1/nexo/build/{os_kind}", response_model=NexoBuildResponse)
async def nexo_build(os_kind: Literal["linux", "windows"], x_bridge_token: str | None = Header(default=None)):
    _check_token(x_bridge_token)
    return await asyncio.to_thread(build_agent, os_kind)
```

- [ ] **Step 5: Run the bridge tests**

Run: `cd backend && .venv/bin/python -m pytest app/tests/test_nexo_host_builds.py -q`

Expected: PASS, including invalid-platform and failed-build redaction cases.

- [ ] **Step 6: Commit the bridge boundary**

```bash
git add host-bridge/nexo_builds.py host-bridge/app.py backend/app/tests/test_nexo_host_builds.py
git commit -m "Nexo: add fixed agent build bridge"
```

### Task 3: Catalog and verify reusable build artifacts

**Files:**
- Create: `backend/app/core/nexo_builds.py`
- Create: `backend/app/api/schemas/nexo_installation.py`
- Create: `backend/app/api/routes/nexo_installation.py`
- Modify: `backend/app/core/config.py`
- Modify: `backend/app/main.py`
- Modify: `docker-compose.yml`
- Test: `backend/app/tests/test_nexo_build_routes.py`

**Interfaces:**
- Produces: `inspect_nexo_source() -> NexoSource`, `build_platform(os_kind) -> NexoAgentBuild`, `GET/POST /api/v1/nexo-agent-builds`.
- Consumes: Task 1 models and Task 2 bridge responses.

- [ ] **Step 1: Write failing route tests**

```python
async def test_build_refresh_reuses_ready_sha_platform(client, admin_headers, fake_bridge, artifact_root):
    fake_bridge.source("a" * 40, "v1.2.3")
    fake_bridge.build("linux", artifact_root / ("a" * 40) / "linux/nexo-remote-agent", b"linux")
    first = await client.post("/api/v1/nexo-agent-builds", headers=admin_headers)
    second = await client.post("/api/v1/nexo-agent-builds", headers=admin_headers)
    assert first.status_code == second.status_code == 202
    assert fake_bridge.build_calls == ["linux", "windows"]

async def test_build_refuses_artifact_outside_root(client, admin_headers, fake_bridge):
    fake_bridge.return_path("../../etc/passwd")
    response = await client.post("/api/v1/nexo-agent-builds", headers=admin_headers)
    assert response.status_code == 502
```

- [ ] **Step 2: Run tests and verify endpoint absence**

Run: `cd backend && POSTGRES_HOST=127.0.0.1 .venv/bin/python -m pytest app/tests/test_nexo_build_routes.py -q`

Expected: FAIL/404 for the missing route.

- [ ] **Step 3: Implement bridge client and artifact validation**

Add settings `NEXO_ARTIFACT_ROOT: Path = Path("/tmp/forgehub-nexo-artifacts")` and `NEXO_INGESTION_URL: str`. Resolve bridge relative paths under the configured root with `Path.resolve()` plus `relative_to(root)`; independently re-read size and checksum before `ready`. Translate bridge timeout/unavailability to safe 502/504 errors and persist bounded failure details.

- [ ] **Step 4: Implement admin list/refresh endpoints and schemas**

`GET` returns `source`, ordered build rows, and never paths. `POST` locks/reuses `(git_sha, os_kind)`, creates `queued -> building -> ready|failed` transitions, and returns 202 projections for both platforms. Use `Depends(get_current_admin)` explicitly.

- [ ] **Step 5: Mount persistent artifacts in deployment**

Add `/root/forgehub-data/nexo-agent-artifacts:/nexo-artifacts:ro` to the backend and configure the host bridge to write `/root/forgehub-data/nexo-agent-artifacts`; set backend `NEXO_ARTIFACT_ROOT=/nexo-artifacts`. Do not alter unrelated existing compose changes.

- [ ] **Step 6: Run focused tests and lint**

Run: `cd backend && POSTGRES_HOST=127.0.0.1 .venv/bin/python -m pytest app/tests/test_nexo_build_routes.py -q`

Run: `cd backend && .venv/bin/ruff check app/core/nexo_builds.py app/api/routes/nexo_installation.py app/api/schemas/nexo_installation.py`

Expected: PASS.

- [ ] **Step 7: Commit the build catalog slice**

```bash
git add backend/app/core/nexo_builds.py backend/app/api/schemas/nexo_installation.py backend/app/api/routes/nexo_installation.py backend/app/core/config.py backend/app/main.py backend/app/tests/test_nexo_build_routes.py docker-compose.yml
git commit -m "Nexo: catalog reusable agent builds"
```

### Task 4: Generate and stream secure workstation packages

**Files:**
- Create: `backend/app/core/nexo_packages.py`
- Modify: `backend/app/api/routes/nexo_installation.py`
- Modify: `frontend/src/lib/api.ts`
- Test: `backend/app/tests/test_nexo_package_routes.py`
- Test: `frontend/src/lib/api.test.ts`

**Interfaces:**
- Produces: `materialize_package(workstation, build, raw_token, destination) -> PackageMetadata`; authenticated `POST /api/v1/workstations/{id}/installation-package?build_id=<uuid>` returning `application/zip`; `apiClient.postDownload(path, body?)`.
- Consumes: ready build artifact, workstation token hashing, configured HTTPS ingestion URL.

- [ ] **Step 1: Write failing ZIP contract tests**

```python
async def test_linux_package_contains_only_fixed_entries(client, admin_headers, ready_linux_build, workstation):
    response = await client.post(f"/api/v1/workstations/{workstation.id}/installation-package?build_id={ready_linux_build.id}", headers=admin_headers)
    assert response.status_code == 200
    with ZipFile(BytesIO(response.content)) as archive:
        assert set(archive.namelist()) == {"nexo-remote-agent", "agent.yaml", "install.sh", "manifest.json", "README.txt"}
        config = yaml.safe_load(archive.read("agent.yaml"))
        assert config["device_token"].startswith("nxw_")
        assert config["endpoint_url"].startswith("https://")
        assert "device_token" not in json.loads(archive.read("manifest.json"))
```

Also test Windows entries, binary checksum, path modes, non-admin 403, OS mismatch 409, non-ready build 409, no token mutation on materialization failure, and a second request invalidating the first token.

- [ ] **Step 2: Run focused tests and confirm endpoint failure**

Run: `cd backend && POSTGRES_HOST=127.0.0.1 .venv/bin/python -m pytest app/tests/test_nexo_package_routes.py -q`

Expected: FAIL because the endpoint/package builder is absent.

- [ ] **Step 3: Implement deterministic package content**

Use `tempfile.TemporaryDirectory`, `zipfile.ZipFile`, fixed archive names, YAML safe serialization, JSON sorted keys, and platform-specific defaults. Linux `install.sh` installs binary/config permissions and systemd unit; Windows `install.ps1` installs files/ACL and creates or replaces the `NexoRemoteAgent` service using fixed commands. Neither script accepts untrusted command fragments.

- [ ] **Step 4: Implement transactional token rotation and response cleanup**

Fully validate/materialize ZIP first. Lock the workstation and current installation with `SELECT ... FOR UPDATE`, generate `nxw_<urlsafe>`, store only its SHA-256, update/create current installation to `package_ready`, reset delivery/report timestamps, append `package_generated`, and commit. Return a `StreamingResponse` whose iterator marks `downloaded` and appends its event only after yielding the final chunk; its `finally` block always removes the temporary directory. A disconnect before iterator completion retains `package_ready`.

- [ ] **Step 5: Add authenticated POST file download support**

```typescript
async function postDownload(path: string, body?: unknown): Promise<{ blob: Blob; filename: string }> {
  const response = await fetch(buildUrl(path), {
    method: "POST",
    headers: { Authorization: `Bearer ${getToken()}`, "Content-Type": "application/json" },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  if (!response.ok) throw await apiErrorFromResponse(path, response);
  return { blob: await response.blob(), filename: filenameFromDisposition(response) };
}
```

Refactor existing download error/filename parsing helpers so GET and POST downloads share them.

- [ ] **Step 6: Run backend and frontend focused tests**

Run: `cd backend && POSTGRES_HOST=127.0.0.1 .venv/bin/python -m pytest app/tests/test_nexo_package_routes.py -q`

Run: `cd frontend && npm test -- src/lib/api.test.ts`

Expected: PASS.

- [ ] **Step 7: Commit the package slice**

```bash
git add backend/app/core/nexo_packages.py backend/app/api/routes/nexo_installation.py backend/app/tests/test_nexo_package_routes.py frontend/src/lib/api.ts frontend/src/lib/api.test.ts
git commit -m "Nexo: deliver one-time installer packages"
```

### Task 5: Reconcile installation state from authenticated reports

**Files:**
- Create: `backend/app/core/nexo_installation_state.py`
- Modify: `backend/app/api/routes/agent_report.py`
- Test: `backend/app/tests/test_nexo_report_reconciliation.py`

**Interfaces:**
- Produces: `reconcile_installation_report(db, workstation, agent_version, reported_at) -> None`.
- Consumes: current installation/build and an already authenticated current workstation token.

- [ ] **Step 1: Write failing state-transition tests**

```python
async def test_first_matching_report_marks_installation_online(client, current_package):
    response = await client.post("/api/v1/agent-reports", headers={"X-Device-Token": current_package.token}, json=report(agent_version=current_package.version))
    assert response.status_code == 202
    installation = await load_installation(current_package.workstation_id)
    assert installation.status == "online"
    assert installation.online_at is not None
    assert await event_types(installation.id) == ["package_generated", "downloaded", "first_report"]
```

Add tests for mismatch -> `outdated`, mismatch detail changes, repeated matching reports without duplicate `first_report`, report without installation compatibility, and an old rotated token returning 401 before reconciliation.

- [ ] **Step 2: Run reconciliation tests and verify current state remains unchanged**

Run: `cd backend && POSTGRES_HOST=127.0.0.1 .venv/bin/python -m pytest app/tests/test_nexo_report_reconciliation.py -q`

Expected: FAIL because reports only update workstation heartbeat/version.

- [ ] **Step 3: Implement a transaction-local state machine**

Lock the installation/build row, ignore absence, require `reported_at >= package_generated_at`, set `online_at` only once, append `first_report` once, compare the exact reported version to `build.agent_version`, and append `version_mismatch` only on entry or changed mismatch detail. Do not catch/commit separately: the heartbeat, irregularities, and installation transition remain one transaction.

- [ ] **Step 4: Call reconciliation from ingestion before commit**

```python
reported_at = datetime.now(timezone.utc)
workstation.last_report_at = reported_at
if report.agent_version:
    workstation.last_seen_agent_version = report.agent_version
await reconcile_installation_report(db, workstation, report.agent_version, reported_at)
await db.commit()
```

- [ ] **Step 5: Run reconciliation and existing ingestion tests**

Run: `cd backend && POSTGRES_HOST=127.0.0.1 .venv/bin/python -m pytest app/tests/test_nexo_report_reconciliation.py app/tests/test_agent_report_ingestion.py -q`

Expected: PASS.

- [ ] **Step 6: Commit report reconciliation**

```bash
git add backend/app/core/nexo_installation_state.py backend/app/api/routes/agent_report.py backend/app/tests/test_nexo_report_reconciliation.py
git commit -m "Nexo: confirm installs from agent reports"
```

### Task 6: Expose installation list, filters, and history

**Files:**
- Modify: `backend/app/api/schemas/nexo_installation.py`
- Modify: `backend/app/api/routes/nexo_installation.py`
- Test: `backend/app/tests/test_nexo_installation_routes.py`

**Interfaces:**
- Produces: `GET /api/v1/nexo-installations?client_id=&os_kind=&status=&workstation_id=` and `GET /api/v1/nexo-installations/{id}`.
- Consumes: Task 1 persistence and client/workstation/build joins.

- [ ] **Step 1: Write failing projection/filter tests**

```python
async def test_list_installations_filters_and_projects_names(client, auth_headers, online_installation):
    response = await client.get("/api/v1/nexo-installations", params={"status": "online", "client_id": str(online_installation.client_id)}, headers=auth_headers)
    assert response.status_code == 200
    row = response.json()[0]
    assert row["client_name"] == online_installation.client_name
    assert row["workstation_hostname"] == online_installation.hostname
    assert row["expected_version"] == online_installation.version

async def test_detail_returns_oldest_to_newest_events(client, auth_headers, installation):
    response = await client.get(f"/api/v1/nexo-installations/{installation.id}", headers=auth_headers)
    assert [event["event_type"] for event in response.json()["events"]] == ["package_generated", "downloaded"]
```

- [ ] **Step 2: Run tests and observe missing list/detail behavior**

Run: `cd backend && POSTGRES_HOST=127.0.0.1 .venv/bin/python -m pytest app/tests/test_nexo_installation_routes.py -q`

Expected: FAIL/404.

- [ ] **Step 3: Implement typed filters and joined projections**

Reject unsupported `os_kind/status` with 422, order rows by client name/hostname, include expected/detected versions and timestamps, and return event history ordered by `(created_at, id)`. Never include artifact paths, token hashes, or raw tokens.

- [ ] **Step 4: Run focused tests and lint**

Run: `cd backend && POSTGRES_HOST=127.0.0.1 .venv/bin/python -m pytest app/tests/test_nexo_installation_routes.py -q`

Run: `cd backend && .venv/bin/ruff check app/api/routes/nexo_installation.py app/api/schemas/nexo_installation.py`

Expected: PASS.

- [ ] **Step 5: Commit query APIs**

```bash
git add backend/app/api/schemas/nexo_installation.py backend/app/api/routes/nexo_installation.py backend/app/tests/test_nexo_installation_routes.py
git commit -m "Nexo: expose installation status history"
```

### Task 7: Build the Nexo agents administration page

**Files:**
- Create: `frontend/src/hooks/useNexoInstallations.ts`
- Create: `frontend/src/pages/nexo-agents/index.tsx`
- Create: `frontend/src/pages/nexo-agents/index.test.tsx`
- Create: `frontend/src/i18n/locales/en/nexoAgents.json`
- Create: `frontend/src/i18n/locales/pt-BR/nexoAgents.json`
- Create: `frontend/src/i18n/locales/es/nexoAgents.json`
- Modify: `frontend/src/i18n/index.ts`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/navSections.ts`
- Modify: `frontend/src/components/layout/navSections.test.tsx`
- Modify: `frontend/src/i18n/locales/en/common.json`
- Modify: `frontend/src/i18n/locales/pt-BR/common.json`
- Modify: `frontend/src/i18n/locales/es/common.json`

**Interfaces:**
- Produces: `/nexo-agents`, `useNexoBuilds`, `useRefreshNexoBuilds`, `useNexoInstallations`, `useNexoInstallation`, and `useGenerateNexoPackage`.
- Consumes: Tasks 3, 4, and 6 API contracts plus `apiClient.postDownload`.

- [ ] **Step 1: Read the two required frontend design skills and update `DESIGN.md` only if their guidance requires it**

Run the skill instructions before making UI choices. Preserve ForgeHub's existing layout, typography, semantic badges, table density, confirmation-dialog behavior, and responsive conventions.

- [ ] **Step 2: Write failing page and navigation tests**

```tsx
it("filters installations and identifies state without color alone", async () => {
  renderNexoAgents();
  expect(screen.getByRole("heading", { name: "Agentes Nexo" })).toBeInTheDocument();
  fireEvent.change(screen.getByLabelText("Status"), { target: { value: "outdated" } });
  expect(screen.getByText("Desatualizado")).toBeInTheDocument();
  expect(screen.queryByText("Online")).not.toBeInTheDocument();
});

it("confirms token rotation before generating and saving the package", async () => {
  renderNexoAgents();
  fireEvent.click(screen.getByRole("button", { name: /gerar e baixar/i }));
  expect(screen.getByRole("dialog")).toHaveTextContent("token anterior deixará de funcionar");
  fireEvent.click(screen.getByRole("button", { name: /confirmar geração/i }));
  await waitFor(() => expect(mocks.generatePackage).toHaveBeenCalledWith(expect.objectContaining({ workstationId: "ws-1" })));
});
```

Test build loading/failure/retry, empty and partial data, filters, history dialog, stable mutation error region, and navigation placement under Operations.

- [ ] **Step 3: Run the page tests and confirm missing modules/routes fail**

Run: `cd frontend && npm test -- src/pages/nexo-agents/index.test.tsx src/components/layout/navSections.test.tsx`

Expected: FAIL because the page/hooks/nav entry do not exist.

- [ ] **Step 4: Implement typed hooks and browser save behavior**

After `postDownload`, create an object URL, click a temporary anchor with the server filename, revoke the URL, then invalidate `nexo-builds`, `nexo-installations`, and `workstations`. Keep selected client/OS/status in URL search parameters so client-detail links can prefilter the page.

- [ ] **Step 5: Implement the accessible responsive page**

Use `AppLayout` via the existing nested route. Render compact source/build controls, explicit platform status, labeled filters, table rows with text+icon state, detected/expected versions, package/heartbeat time, generate-download action, and history dialog. Provide skeleton/loading, empty, partial/error/retry, mutation pending, disabled, and stable error regions. Require the existing `ConfirmDialog` before token rotation.

- [ ] **Step 6: Register route, navigation, namespace, and three locale files**

Add `nexoAgents` to `NAMESPACES`, lazy/static page import following `App.tsx` conventions, route `nexo-agents`, Operations link under `clients` module, and complete matching key topology in all three JSON files.

- [ ] **Step 7: Run page tests and build**

Run: `cd frontend && npm test -- src/pages/nexo-agents/index.test.tsx src/components/layout/navSections.test.tsx`

Run: `cd frontend && npm run build`

Expected: PASS with no TypeScript errors.

- [ ] **Step 8: Commit the administration page**

```bash
git add frontend/src/hooks/useNexoInstallations.ts frontend/src/pages/nexo-agents frontend/src/i18n/index.ts frontend/src/i18n/locales/en/nexoAgents.json frontend/src/i18n/locales/pt-BR/nexoAgents.json frontend/src/i18n/locales/es/nexoAgents.json frontend/src/App.tsx frontend/src/components/layout/navSections.ts frontend/src/components/layout/navSections.test.tsx frontend/src/i18n/locales/en/common.json frontend/src/i18n/locales/pt-BR/common.json frontend/src/i18n/locales/es/common.json DESIGN.md
git commit -m "Nexo: add installer monitoring area"
```

If `DESIGN.md` was not changed, omit it from `git add`.

### Task 8: Add contextual controls to client detail

**Files:**
- Modify: `frontend/src/pages/clients/[id].tsx`
- Modify: `frontend/src/pages/clients/index.test.tsx`
- Modify: `frontend/src/i18n/locales/en/clients.json`
- Modify: `frontend/src/i18n/locales/pt-BR/clients.json`
- Modify: `frontend/src/i18n/locales/es/clients.json`

**Interfaces:**
- Produces: workstation installation badge, generate/download confirmation, and prefiltered history link on client detail.
- Consumes: Task 7 hooks and `/nexo-agents?client_id=<id>&workstation_id=<id>`.

- [ ] **Step 1: Extend client detail tests first**

```tsx
it("shows installation state and links to filtered history", () => {
  renderAt("/clients/client-1", <ClientDetailPage />, "/clients/:id");
  expect(screen.getByText("Online")).toBeInTheDocument();
  expect(screen.getByRole("link", { name: /ver histórico/i })).toHaveAttribute(
    "href", "/nexo-agents?client_id=client-1&workstation_id=ws-a",
  );
});
```

Add a test proving generation still requires confirmation and invokes the same hook as the primary page.

- [ ] **Step 2: Run the client page tests and confirm the new expectations fail**

Run: `cd frontend && npm test -- src/pages/clients/index.test.tsx`

Expected: FAIL because installation controls are absent.

- [ ] **Step 3: Add concise status/actions without duplicating history UI**

Join installation projections by workstation ID, render text+icon badge, a `Generate and download` action using the shared confirmation flow, and a filtered history link. Preserve the existing peer-grant section and stable pending/error layout.

- [ ] **Step 4: Complete three-language client copy and run tests/build**

Run: `cd frontend && npm test -- src/pages/clients/index.test.tsx src/pages/nexo-agents/index.test.tsx`

Run: `cd frontend && npm run build`

Expected: PASS.

- [ ] **Step 5: Commit client integration**

```bash
git add frontend/src/pages/clients/'[id].tsx' frontend/src/pages/clients/index.test.tsx frontend/src/i18n/locales/en/clients.json frontend/src/i18n/locales/pt-BR/clients.json frontend/src/i18n/locales/es/clients.json
git commit -m "Clients: expose Nexo installation actions"
```

### Task 9: Verify the full delivery and update operator documentation

**Files:**
- Modify: `docs/PENDENCIAS.md`
- Modify: `docs/README.md` only if its existing pending link needs correction
- Create: `docs/runbooks/NEXO_AGENT_PACKAGES.md`

**Interfaces:**
- Produces: reproducible build/package/report verification evidence and operating instructions.
- Consumes: all earlier tasks.

- [ ] **Step 1: Run complete relevant backend verification**

Run: `cd backend && POSTGRES_HOST=127.0.0.1 .venv/bin/python -m alembic current`

Run: `cd backend && POSTGRES_HOST=127.0.0.1 .venv/bin/python -m pytest app/tests/test_nexo_installation_models.py app/tests/test_nexo_host_builds.py app/tests/test_nexo_build_routes.py app/tests/test_nexo_package_routes.py app/tests/test_nexo_report_reconciliation.py app/tests/test_nexo_installation_routes.py app/tests/test_agent_report_ingestion.py app/tests/test_workstation_routes.py -q`

Run: `cd backend && .venv/bin/ruff check app`

Expected: current migration at head; all tests and lint PASS.

- [ ] **Step 2: Run complete relevant frontend verification**

Run: `cd frontend && npm test -- src/pages/nexo-agents/index.test.tsx src/pages/clients/index.test.tsx src/components/layout/navSections.test.tsx src/lib/api.test.ts`

Run: `cd frontend && npm run build`

Expected: all tests and production build PASS.

- [ ] **Step 3: Perform a synthetic end-to-end package check**

Create a test-only workstation, request Linux and Windows builds, generate each ZIP, verify fixed entry names and manifest SHA against the extracted binary, send one authenticated synthetic agent report using the package token, and confirm the installation transitions to `online`. Never use a production workstation or token; delete the synthetic records and temporary extracted files afterward.

- [ ] **Step 4: Document operation and evidence**

Document artifact paths/configuration, build refresh, package generation, one-time token consequences, status meanings, recovery from `failed`/`package_ready`/`outdated`, and verification commands in `docs/runbooks/NEXO_AGENT_PACKAGES.md`. Update `docs/PENDENCIAS.md` by moving only the delivered installer/monitoring items to `concluído` and recording exact command results; leave Headscale, Darckware, deploy, and reports unchanged.

- [ ] **Step 5: Check the final diff for accidental secrets and unrelated files**

Run: `git diff --check`

Run: `git diff | rg -n 'nxw_|AAG[A-Za-z0-9_-]{20,}|device_token:'`

Expected: whitespace check passes and no real token is present; test fixture values are clearly synthetic.

- [ ] **Step 6: Commit verification documentation**

```bash
git add docs/PENDENCIAS.md docs/README.md docs/runbooks/NEXO_AGENT_PACKAGES.md
git commit -m "Docs: record Nexo installer operations"
```

- [ ] **Step 7: Apply completion workflow**

Read and use `superpowers:verification-before-completion`, then `superpowers:requesting-code-review`. After review findings are resolved and verification rerun, use `superpowers:finishing-a-development-branch` to present integration options without automatically merging.
