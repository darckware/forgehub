# ForgeHub — Data Specification (DATA SPEC)

Canonical artifact referenced by `docs/SPEC.md` §12 ("Next Spec Artifacts" → DATA SPEC). This document is the data dictionary and entity-relationship map for every table ForgeHub owns in the `company` schema of the shared `company_postgres` instance (topology: `docs/DB_README.md`).

Ground truth is `backend/app/db/models/*.py` — if this document and the code disagree, the code wins; update this file.

## 1. Conventions

- All tables use a Python-side `UUID` primary key (`default=uuid.uuid4`), never DB-generated, never autoincrement — IDs must exist before flush/commit (`backend/app/db/base.py`).
- Every table has `created_at`/`updated_at` via `TimestampMixin`.
- Cross-domain foreign keys are plain string-form `ForeignKey("company.<table>.id")`, never backed by a cross-module model import or `relationship()` — this keeps domain modules independent at import time. They are resolved lazily once `app/db/models/__init__.py` imports every domain module.
- Status/type fields are plain `String` + a `CheckConstraint` listing the allowed values (not native Postgres `ENUM`) — except `Artifact.artifact_type`/`status` and `ArtifactVersion.status`, which use native Postgres enums (`Enum(...)`), and `agents`/`sub_agents`/`skills` statuses, which follow the `CheckConstraint` convention like the rest.
- Polymorphic references (`Approval`, `AuditEvent`) use a plain `(entity_type: str, entity_id: UUID)` pair instead of a real FK, since they target many different tables.
- Business rules requiring a second statement or cross-row checks (existence of a referenced row, state-machine transitions) are enforced at the API route layer, not the DB — see `docs/BUSINESS_RULES.md`.

## 2. Entity-relationship overview

```
Product ──< ProductModule
   └──< ProductVersion ──< Release
                │
                │ (required FK)
                ▼
             Project ──< ProjectPlan ──< PlanBaseline ──< ChangeRequest
                │  └──< ProjectStructureNode (self M:N tree, optional is_locked)
                │                                              ▲
                │ (required FK, API-enforced)                 │ (optional FK)
                ▼                                              │
           PlanningItem ──< VersionScopeItem >── ProductVersion │
           PlanningItem ──< (1:1) FeatureRequest / BugReport ───┘
           PlanningItem ── (optional FK) ──> ProjectStructureNode
                │ (required FK, API-enforced)
                ▼
           ProjectTask ──< TaskDependency (self M:N)
                │      ──< TaskRequiredSkill >── Skill
                │      ──< TaskAssignment >── Agent | SubAgent  (exactly one, schema-enforced)
                └──< TaskExecution
                          │
                          ▼
                      Artifact (optional FK → PipelineStage, → TaskExecution)
                          └──< ArtifactVersion (optional FK → TaskExecution)

ProjectPipeline (required FK → Project) [optionally instantiated from PipelineTemplate]
   └──< PipelineStage ──< PipelineStageDependency (self M:N)
                      ──< PipelineStageRequiredArtifact (optional FK → Artifact)
                      └──< PipelineStageGate

PipelineTemplate ──< PipelineTemplateStage ──< PipelineTemplateRequiredArtifact

Agent ──< SubAgent ──< AgentSkill / SubAgentSkill >── Skill
   └──< AgentCostRate, AgentCapacity

Approval, AuditEvent: polymorphic (entity_type, entity_id) → any table above. No real FK.
Policy: standalone governance rule registry, optionally referenced by Approval.policy_id.
```

## 3. Data dictionary

### 3.1 Product domain (`backend/app/db/models/product.py`)

| Table | Column | Type | Required | Notes |
|---|---|---|---|---|
| `products` | id | UUID | PK | |
| | name | String(255) | yes, unique | |
| | description | Text | no | |
| `product_modules` | id | UUID | PK | |
| | product_id | UUID FK→products (CASCADE) | yes | |
| | name | String(255) | yes | unique per product |
| | description | Text | no | |
| `product_versions` | id | UUID | PK | |
| | product_id | UUID FK→products (CASCADE) | yes | |
| | version | String | yes | unique per product |
| | status | String, CHECK | yes, default `planned` | `planned\|in_development\|in_test\|published\|deprecated` |
| | release_notes | Text | no | |
| `releases` | id | UUID | PK | |
| | product_version_id | UUID FK→product_versions (CASCADE) | yes | |
| | name | String(255) | yes | |
| | status | String, CHECK | yes, default `draft` | `draft\|ready\|released\|cancelled` |
| | notes | Text | no | |

> **Gap (flagged, not fixed):** `Release` has full backend CRUD (`backend/app/api/routes/product.py`) but no frontend page/hook — currently unreachable from the UI. See `docs/screens/` notes.

### 3.2 Project domain (`backend/app/db/models/project.py`)

| Table | Column | Type | Required | Notes |
|---|---|---|---|---|
| `projects` | id | UUID | PK | |
| | name | String(255) | yes | |
| | description | Text | no | |
| | product_version_id | UUID FK→product_versions | yes | |
| | owner | String(255) | no | |
| | status | String, CHECK | yes, default `planned` | `planned\|active\|on_hold\|completed\|cancelled` (constraint added in migration `c36149f00511`) |
| | start_date / target_end_date | Date | no | |
| | working_directory_path | String(1024) | no | **added this session** — on-disk path of the project's real code/repo, e.g. `/root/project/forgehub` |
| `project_structure_nodes` | id | UUID | PK | **added this session** |
| | project_id | UUID FK→projects | yes | |
| | parent_node_id | UUID FK→project_structure_nodes (self) | no | builds a tree |
| | name | String(255) | yes | |
| | node_type | String, CHECK | yes | `folder\|module\|component\|screen\|table\|stored_procedure` |
| | path | String(1024) | no | relative to the owning project's `working_directory_path` |
| | description | Text | no | |
| | is_locked | Boolean | yes, default false | advisory "finalized, do not alter" flag — see §6 below |
| `project_plans` | id | UUID | PK | |
| | project_id | UUID FK→projects | yes | |
| | name | String(255) | yes | |
| | scope_summary | Text | no | |
| | estimated_start/end_date | Date | no | |
| | estimated_cost | Numeric(14,2) | no | |
| | status | String, CHECK | yes, default `draft` | `draft\|approved\|baselined\|superseded` |
| | approved_at | DateTime(tz) | no | |
| `plan_baselines` | id | UUID | PK | |
| | project_plan_id | UUID FK→project_plans | yes | |
| | name | String(255) | yes | |
| | scope_snapshot / cost_snapshot / end_date_snapshot | mixed | no | frozen copy of the plan at baseline time |
| | frozen_at | DateTime(tz) | yes, default now | |
| `change_requests` | id | UUID | PK | |
| | project_id | UUID FK→projects | yes | |
| | plan_baseline_id | UUID FK→plan_baselines | no | |
| | title | String(255) | yes | |
| | justification | Text | no | |
| | affects_scope/schedule/cost, adds_features, removes_features, introduces_critical_bug_fix, changes_agents/skills/architecture/security | Boolean | yes, default false | SPEC 6.3.3 impact flags |
| | schedule_delta_days | Integer | no | |
| | cost_delta | Numeric(14,2) | no | |
| | status | String, CHECK | yes, default `pending` | `pending\|approved\|rejected\|applied` (constraint added in migration `c36149f00511`) |
| | requested_by | String(255) | no | |
| | decided_at | DateTime(tz) | no | |

### 3.3 Pipeline domain (`backend/app/db/models/pipeline.py`)

| Table | Column | Type | Required | Notes |
|---|---|---|---|---|
| `pipeline_templates` | id, name (unique), description, is_active | — | name required | reusable pipeline definition |
| `pipeline_template_stages` | id, template_id (FK, required), name, stage_type, order_index, requires_approval, requires_verification | — | required | unique per (template_id, order_index) |
| `pipeline_template_required_artifacts` | id, template_stage_id (FK, required), artifact_type, is_mandatory | — | required | |
| `project_pipelines` | id, project_id (FK, required), template_id (FK, optional), name, status (default `active`), is_active | — | | |
| `pipeline_stages` | id, pipeline_id (FK, required), name, stage_type, order_index, status (default `pending`), requires_approval, requires_verification | — | | unique per (pipeline_id, order_index) |
| `pipeline_stage_dependencies` | id, stage_id (FK, required), depends_on_stage_id (FK, required) | — | | unique pair |
| `pipeline_stage_required_artifacts` | id, stage_id (FK, required), artifact_type, is_mandatory, artifact_id (FK, optional), is_fulfilled | — | | |
| `pipeline_stage_gates` | id, stage_id (FK, required), gate_type (`approval`\|`verification`), name, is_mandatory, status (default `pending`), approved_by | — | | |

No `CheckConstraint` exists yet on `pipeline_stages.status` / `project_pipelines.status` / `pipeline_stage_gates.status` — these remain free strings today; flagged as a possible follow-up hardening pass, out of scope for this round (see `docs/BUSINESS_RULES.md` §7).

### 3.4 Backlog domain (`backend/app/db/models/backlog.py`)

| Table | Column | Type | Required | Notes |
|---|---|---|---|---|
| `planning_items` | id, title, item_type (CHECK), status (CHECK, default `new`), priority (default `medium`), project_id (FK, nullable at DB / **required at API**), target_version_id (FK, nullable by design), structure_node_id (FK→project_structure_nodes, optional, **added this session**), baselined (bool, default false) | — | | `item_type` ∈ feature\|bug\|hotfix\|improvement\|technical_debt\|refactoring\|security_fix\|research\|documentation; `status` ∈ new\|triaged\|scoped\|baselined\|in_progress\|done\|rejected\|cancelled |
| `feature_requests` | id, title, description, requested_by, business_value, planning_item_id (FK, nullable unique) | — | | intake row; converts 1:1 into a PlanningItem |
| `bug_reports` | id, title, description, severity (CHECK low\|medium\|high\|critical), environment, reproduction_steps, root_cause, detected_version_id (FK), fixed_in_version_id (FK), planning_item_id (FK, nullable unique) | — | | |
| `version_scope_items` | id, planning_item_id (FK, required), product_version_id (FK, required), notes | — | | unique pair; only allowed once the planning item is past `new` status |
| `triage_decisions` | id, planning_item_id (FK, required), outcome (CHECK accepted\|rejected\|deferred\|merged\|duplicate), rationale, decided_by | — | | append-only decision log |

### 3.5 Task domain (`backend/app/db/models/task.py`)

| Table | Column | Type | Required | Notes |
|---|---|---|---|---|
| `project_tasks` | id, planning_item_id (FK, nullable at DB / **required at API**), parent_task_id (self-FK, optional), title, description, task_type (default `feature`), status (CHECK, default `planned`), priority (default `medium`), estimated/actual_cost, planned_start/end_date, started_at, completed_at | — | | status set ∈ planned\|assigned\|in_progress\|blocked\|done\|deployed\|cancelled — `CheckConstraint` added in migration `3d0bb9a16778` (**this session**; previously schema-validated only, no DB CHECK — see `docs/BUSINESS_RULES.md` §11) |
| `task_dependencies` | id, task_id (FK, required), depends_on_task_id (FK, required), dependency_type (default `finish_to_start`) | — | | |
| `task_required_skills` | id, task_id (FK, required), skill_id (FK, required), is_mandatory, minimum_proficiency | — | | |
| `task_assignments` | id, task_id (FK, required), agent_id (FK, optional), sub_agent_id (FK, optional), status (default `active`), assigned_at, unassigned_at | — | | exactly one of agent_id/sub_agent_id enforced by a Pydantic `model_validator` (schema layer), not a DB constraint |
| `task_executions` | id, task_id (FK, required), assignment_id (FK, optional), attempt_number (server-assigned), executor_type (default `agent`), status (default `pending`), started_at, finished_at, outcome_summary, evidence_ref, actual_cost | — | | `evidence_ref` required once status reaches `verified`/`completed` (schema + route re-check) |

### 3.6 Artifact domain (`backend/app/db/models/artifact.py`)

| Table | Column | Type | Required | Notes |
|---|---|---|---|---|
| `artifacts` | id, name, artifact_type (native Postgres enum), status (native enum, default `DRAFT`), description, pipeline_stage_id (FK, optional — existence-validated when set), task_execution_id (FK, optional — existence-validated when set), requires_approval, is_locked (bool, default false, **added this session**) | — | | `artifact_type` ∈ prd\|spec\|data_spec\|business_rule_spec\|security_spec\|source_code\|migration\|test_report\|release_notes\|pull_request\|deployment_package\|approval_record\|screen\|component\|report\|database_schema\|table\|stored_procedure\|reference_doc\|context_brief\|other (8 fine-grained values added in migration `91bd82affb72`); `status` ∈ draft\|submitted\|approved\|rejected\|superseded |
| `artifact_versions` | id, artifact_id (FK, required, CASCADE), version_number (server-assigned, unique per artifact), status (native enum DRAFT\|FINAL\|SUPERSEDED), location_uri (required — path/URL, not inline content), checksum, notes, produced_by_task_execution_id (FK, optional) | — | | |

> **Superseded decision:** an earlier round of this session deferred adding fine-grained artifact types (screen/component/table/etc.), registering screen specs as `spec` and the tech-stack doc as `other`. Revisited and reversed later in the same session — see `docs/BUSINESS_RULES.md` §8.

### 3.7 Governance domain (`backend/app/db/models/governance.py`)

| Table | Column | Type | Required | Notes |
|---|---|---|---|---|
| `policies` | id, name (unique, required), description, policy_type (required), rules (JSONB), is_active (default true) | — | | |
| `approvals` | id, entity_type + entity_id (polymorphic target, required), approval_type (required), status (default `pending`), policy_id (FK, optional), requested_by (required), decided_by, comments | — | | deciding writes a companion `AuditEvent` |
| `audit_events` | id, entity_type + entity_id (polymorphic target, required), event_type (required), actor (required), payload (JSONB) | — | | append-only; now auto-written by the route layer on: `ProjectTask` → `done`, `TaskExecution` → `verified`/`completed`, `PipelineStage` → `completed`, `Artifact` → approve/reject |

### 3.8 Agent domain (`backend/app/db/models/agent.py`)

| Table | Column | Type | Required | Notes |
|---|---|---|---|---|
| `agents` | id, name (unique, required), agent_type (CHECK coordinator\|executor\|hybrid, default `executor`), status (CHECK active\|inactive\|retired, default `active`), is_active, profile_slug/layer/runtime_tier/telegram_required/has_profile/mission/source_path (all nullable — populated only by the Hermes Foundation sync) | — | | |
| `sub_agents` | id, agent_id (FK, required, CASCADE), name (unique per agent), status (same CHECK set), permission_scope | — | | |
| `skills` | id, name + version (unique pair, required), origin (CHECK internal\|third_party\|foundation), risk_level (CHECK low\|medium\|high\|critical), permissions (Text, **required**), is_approved, security_reviewed (bool, default false) | — | | |
| `agent_skills` / `sub_agent_skills` | id, agent_id/sub_agent_id (FK), skill_id (FK) | — | | unique pair association tables |
| `agent_cost_rates` | id, agent_id (FK), rate_unit (CHECK per_task\|per_hour\|per_token\|per_execution), rate_amount (required, ≥0) | — | | |
| `agent_capacities` | id, agent_id (FK, unique), max_concurrent_tasks (required, ≥1) | — | | |

## 4. Known model-vs-data observations

- The live `company_postgres` / `forgehub` database (verified during this session) already has Agent-domain rows from a Hermes Foundation sync (`agents=25`, `sub_agents=98`, `skills=153`) — any pilot/demo data populated for the other domains must reference these existing rows for `TaskAssignment`, not create duplicate placeholder agents.
- `approvals`/`audit_events` had pre-existing rows of unknown origin at the start of this session (32 and 77 respectively, before any of this session's own work) — not cleaned up or assumed to be zero by any process described in this document.
- `pipeline_templates` has zero seeded rows in any environment — there is no default "standard SDLC" template shipped with the app today; one is proposed as part of the ForgeHub pilot project (see `docs/BUSINESS_RULES.md` and the Project entity created for ForgeHub itself in the live system).
- **Kanboard sync (implemented this session, after the gap above was first flagged):** `POST /api/v1/tasks/{id}/sync-kanboard` (`api/routes/task.py`) pushes a `ProjectTask` to the real, already-existing "Forgehub" Kanboard project (id `8`, identifier `FORGECOMPANY` — found live, not created by this work) as a card, via a small JSON-RPC client (`app/core/kanboard_client.py`). Idempotent: `project_tasks.kanboard_task_id` (nullable int, migration `9e2a27998edd`) is set on first sync and reused on every later sync (update + move instead of create). `TASK_STATUS_TO_KANBOARD_COLUMN` in `api/routes/task.py` maps the 7 `TASK_STATUSES` onto Kanboard's existing columns (Backlog/Ready/In Progress/Blocked/Done/Close/Canceled — `deployed` maps to `Close`, Kanboard has no native "deployed" column). The planning-item-level `responsible_agent_id`/`delivery_location` fields discussed earlier remain deferred — this sync is per-`ProjectTask` (one card per task), not per-`PlanningItem`, so they were not needed to ship it. The frontend's "Kanboard" page (`pages/kanboard/index.tsx`) is still just an `<iframe>` of the board for browsing — this sync is a separate, explicit "Sync to Kanboard" action on the task detail page, not automatic on every task mutation.
