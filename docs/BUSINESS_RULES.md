# ForgeHub — Business Rule Specification (BUSINESS RULE SPEC)

Canonical artifact referenced by `docs/SPEC.md` §12 ("Next Spec Artifacts" → BUSINESS RULE SPEC). This document restates the rule list already summarized in `docs/SPEC.md` §6, expands each rule with **where it is enforced in code** (file:line, so the rule can be re-verified against the running implementation), and adds the rules introduced after SPEC.md was last updated.

Convention used throughout the codebase: rules that are single-column constraints live as a DB `CheckConstraint`; rules that require a second statement, a cross-row check, or knowledge of another domain's table live at the API route layer (`backend/app/api/routes/*.py`), never as a DB trigger. See `docs/DATA_MODEL.md` §1.

## 1. Product Rules (SPEC §6.1)

| # | Rule | Enforcement |
|---|---|---|
| 1 | Every product must have a unique name | DB: `products.name` unique constraint (`db/models/product.py`) |
| 2 | A product can have many modules | DB: `product_modules.product_id` FK, no cardinality cap |
| 3 | Every product must have at least one version | API: enforced in `create_product`/`delete_version`, `api/routes/product.py` (deleting the only remaining version is rejected) |
| 4 | Published versions cannot be mutated directly | API: `update_version` rejects edits when `status == "published"`, `api/routes/product.py` |
| 5 | Fixes for published versions must create patch/hotfix flows | Modeled via `BugReport.fixed_in_version_id` + a new `ProductVersion`/`PlanningItem` of type `hotfix` — not a hard gate, by convention |

## 2. Pipeline Rules (SPEC §6.2)

| # | Rule | Enforcement |
|---|---|---|
| 1 | Every project must have an active pipeline | Not auto-created; caller must `POST /pipelines` — see `docs/DATA_MODEL.md` §3.3 gap note |
| 2 | Only one pipeline can be active per project | API: `_deactivate_other_active_pipelines`, `api/routes/pipeline.py` |
| 3 | Every stage must define order, status, and type | Schema: `PipelineStageCreate` required fields |
| 4-5 | Stages may require approval / independent verification | Modeled via `PipelineStageGate.gate_type` (`approval`\|`verification`) |
| 6 | Stages may require mandatory artifacts | `PipelineStageRequiredArtifact.is_mandatory` |
| 7 | A stage cannot complete if mandatory artifacts are missing | API: `_enforce_stage_advance_rules`, `api/routes/pipeline.py` |
| 8 | A stage cannot complete if mandatory gates are unapproved | Same function, gate check |
| 9 | Blocked stages must prevent dependent stages from advancing | Same function, dependency-status check (`_BLOCKING_STAGE_STATUSES`/`_TERMINAL_STAGE_STATUSES`) |
| 10 | Release approval allowed only when all required gates pass | `GET /pipelines/{id}/gates-check`, `api/routes/pipeline.py` |

## 3. Planning Rules (SPEC §6.3)

| # | Rule | Enforcement |
|---|---|---|
| 1 | Approved planning becomes baseline | API: `approve_project_plan` flips status to `approved`; `create_plan_baseline` only allowed from an `approved` plan, `api/routes/project.py` |
| 2 | Post-baseline changes require a Change Request | API: direct plan mutation rejected once a baseline exists, `api/routes/project.py` |
| 3 | Change Requests track scope/time/cost/feature/bug/agent/skill/architecture/security impact | `ChangeRequest` boolean impact-flag columns, `db/models/project.py` |

## 4. Execution Rules (SPEC §6.4)

| # | Rule | Enforcement |
|---|---|---|
| 1 | Planned, assigned, and executed remain distinct states | `ProjectTask.status` transitions driven by side effects of `TaskAssignment`/`TaskExecution` creation, never collapsed into one field — `api/routes/task.py` |
| 2 | Each task can have multiple executions | `TaskExecution.attempt_number` auto-increments per task, `create_task_execution` |
| 3 | Every execution must have evidence | Schema + route re-check: `evidence_ref` required once status is `verified`/`completed`, `api/schemas/task.py` + `update_task_execution` |
| 4 | Every task completion must be auditable | **Implemented this session**: `AuditEvent` auto-written on `ProjectTask`→`done` and `TaskExecution`→`verified`/`completed`, `api/routes/task.py` |

## 5. Skill Rules (SPEC §6.5)

| # | Rule | Enforcement |
|---|---|---|
| 1-3 | Every skill must have a version, an origin, a risk level | DB: `skills.version`/`origin`/`risk_level` required + `CheckConstraint`, `db/models/agent.py` |
| 4 | Every skill must declare permissions | DB: `skills.permissions` required `Text` column |
| 5 | Critical skills require approval | API-layer convention via `Skill.is_approved` + `Approval` polymorphic record |
| 6 | Third-party skills require security review | `Skill.security_reviewed` boolean, checked at the route layer where skills are granted |
| 7 | Sub-agents may only use skills explicit or inherited by permission | `SubAgentSkill` association table + `permission_scope` on `SubAgent` |
| 8 | Approved skills must not change without a new version | Convention: a new `Skill` row (new version) rather than mutating an approved one — mirrored in the Artifact domain's "new version reopens governance review" rule below |

## 6. Traceability Rules (core invariant, added this session — not yet in SPEC.md §6, should be folded in at the next SPEC revision)

These implement the PRD/CLAUDE.md core invariant: *"No feature, bug, task, skill, execution, or artifact may exist without linkage to product, version, project, planning, pipeline, owner, status, audit trail, and validation criteria."* Before this session, the schema allowed several leaf entities to exist disconnected from that chain; the gaps were closed at the API layer (not via DB `NOT NULL`, to avoid an irreversible migration and to follow the project's existing "existence checks belong at the route layer" convention):

| # | Rule | Enforcement |
|---|---|---|
| 1 | A `PlanningItem` must reference an existing `Project` | `create_planning_item`/`update_planning_item` (cannot be cleared), `convert_feature_request`/`convert_bug_report` — all in `api/routes/backlog.py` |
| 2 | A `ProjectTask` must reference an existing `PlanningItem` | `create_task`/`update_task` (cannot be cleared) — `api/routes/task.py` |
| 3 | A `TaskAssignment` must target exactly one of `agent_id`/`sub_agent_id` | Pydantic `model_validator` on `TaskAssignmentCreate` — `api/schemas/task.py` (pre-existing, verified still correct this session) |
| 4 | An `Artifact`'s `pipeline_stage_id`/`task_execution_id`, when provided, must reference existing rows | `_validate_artifact_links`, `api/routes/artifact.py` — links stay **optional** by design (a standalone artifact, e.g. an ad hoc PRD before any pipeline exists, is a valid use case per the model's own docstring), but a *dangling* reference is now rejected |
| 5 | Major entity transitions must write an `AuditEvent` | `ProjectTask`→`done`, `TaskExecution`→`verified`/`completed`, `PipelineStage`→`completed`, `Artifact`→approve/reject — see Execution Rule 4 above and Governance Rule below |

## 7. Governance Rules

| # | Rule | Enforcement |
|---|---|---|
| 1 | Deciding an Approval writes a companion AuditEvent | `decide_approval`-equivalent flow, `api/routes/governance.py` |
| 2 | AuditEvent is append-only (no update/delete endpoints) | Route surface for `audit_events` only exposes create + read, `api/routes/governance.py` |
| 3 | `Project`/`ProjectPlan`/`ChangeRequest` status must be one of a fixed set | **Added this session**: `CheckConstraint` + Pydantic validators, migration `c36149f00511` — previously these three were free strings, inconsistent with every other domain's status field |

### Known remaining inconsistency (flagged, not fixed this round)

`pipeline_stages.status`, `project_pipelines.status`, and `pipeline_stage_gates.status` are still free strings with no `CheckConstraint` — the same class of gap just closed for the Project domain. Left out of this round's scope; candidate for a follow-up hardening pass.

## 8. Artifact Governance: Fine-Grained Types & the `is_locked` Flag (added this session)

| # | Rule | Enforcement |
|---|---|---|
| 1 | `ArtifactType` covers fine-grained deliverables, not just whole documents | `screen`, `component`, `report`, `database_schema`, `table`, `stored_procedure`, `reference_doc`, `context_brief` added to the native enum alongside the original prd/spec/etc. — `db/models/artifact.py`, migration `91bd82affb72`. These are classification labels for *any* project ForgeHub governs — unrelated to ForgeHub's own internal Postgres usage. |
| 2 | A locked `Artifact` or `ProjectStructureNode` cannot be mutated | `Artifact.is_locked` / `ProjectStructureNode.is_locked` (advisory "finalized, do not touch" flag — not a filesystem permission). Every mutating endpoint (`PATCH`, `DELETE`, new version, version edit/delete, approve/reject) returns `409` until explicitly unlocked via `PATCH {"is_locked": false}` — `_assert_not_locked` in `api/routes/artifact.py`, `_assert_node_not_locked` in `api/routes/project.py`. |
| 3 | The lock state must be visible, not just enforced | `is_locked` is part of `ArtifactOut`/`ProjectStructureNodeOut` — an agent reading the resource before acting sees the flag; an agent that tries to write anyway is blocked and told why in the `409` detail message. This is the concrete mechanism behind "don't let an agent alter a finalized module/artifact." |

## 9. Project Structure & Working Directory (added this session)

| # | Rule | Enforcement |
|---|---|---|
| 1 | A project's on-disk working directory must be identifiable | `Project.working_directory_path`, `db/models/project.py` — e.g. `/root/project/forgehub` |
| 2 | A project's real folder/module/screen/table structure can be registered as a tree | `ProjectStructureNode` (self-referencing via `parent_node_id`, `node_type` ∈ folder\|module\|component\|screen\|table\|stored_procedure, `path` relative to `working_directory_path`) — full CRUD at `/api/v1/projects/{project_id}/structure-nodes`, `api/routes/project.py` |
| 3 | A structure node's parent must belong to the same project | `create_structure_node`/`update_structure_node`, `api/routes/project.py` |
| 4 | A `PlanningItem` can point at the specific structure it touches | `PlanningItem.structure_node_id` (optional), validated against `ProjectStructureNode` existence in `create_planning_item`/`update_planning_item`, `api/routes/backlog.py` |

## 10. Standard Pipeline Stage Convention: "Contextualização" (added this session)

PRD/SPEC writing was previously the first stage of the standard pipeline. In practice it has an implicit precondition — gathering business context, stakeholders, constraints, and success criteria — that was happening but never registered anywhere. Since `PipelineStage.stage_type` and `PipelineStageRequiredArtifact.artifact_type` are free strings (no `CheckConstraint`/DB enum — see `db/models/pipeline.py`), this needed no schema change, only a registered convention:

| # | Rule | Convention |
|---|---|---|
| 1 | Every standard pipeline starts with a discovery/context stage, before Documentação | Stage `name="Contextualização"`, `stage_type="context_discovery"`, `order_index=0` (Documentação/Codificação/Banco de Dados/Deploy shift to 1-4) |
| 2 | The stage's deliverable is a context brief, not the PRD itself | Required artifact `artifact_type="context_brief"` (mandatory) — the PRD's required `prd` artifact, now in the Documentação stage, is expected to cite/derive from it |
| 3 | The stage is lightweight by default | `requires_approval=False`, `requires_verification=True` — heavier gating stays reserved for Deploy, consistent with the rest of the standard pipeline |

This is a convention enforced by what gets POSTed when instantiating a pipeline (see `scripts`/pilot population), not a DB constraint — exactly like the rest of `PipelineStage`'s free-string fields.

## 11. ProjectTask Status Set (hardened this session)

`project_tasks.status` was previously a free string with no `CheckConstraint` — and a real bug as a result: the backend's completion logic (dependency checks, the auto-`AuditEvent` rule) keyed off the literal string `"done"`, while the frontend offered `"completed"` as a selectable status that the backend would never itself produce and (once the schema-layer validator below existed) would actually reject.

| # | Rule | Enforcement |
|---|---|---|
| 1 | `status` must be one of a fixed set | `TASK_STATUSES` tuple, `db/models/task.py` + `CheckConstraint`, migration `3d0bb9a16778`; re-exported into `api/schemas/task.py` so the DB constraint and the Pydantic validator can't drift apart |
| 2 | The fixed set is `planned\|assigned\|in_progress\|blocked\|done\|deployed\|cancelled` | `"done"` = finalizada (work finished, evidence verified); `"deployed"` = liberada para produção (shipped to production) — added as a separate, later terminal state per user request, distinct from "done" |
| 3 | `assigned`/`in_progress` are still set automatically as side effects | `create_task_assignment` → `assigned`, `create_task_execution` → `in_progress` (only from `planned`/`assigned`), `api/routes/task.py` — unchanged by this hardening |
