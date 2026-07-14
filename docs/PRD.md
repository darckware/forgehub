# ForgeHub — Product Requirements Document (PRD)

> **Status documental:** baseline original do produto. Este arquivo não contém a arquitetura posterior de concepção, System Blueprint, três macrofluxos, orquestração durável e Delivery. Para a direção atual, consulte `PLANNING_DELIVERY_ARCHITECTURE.md`; para saber o que já existe, confirme código, `DATA_MODEL.md` e `BUSINESS_RULES.md`.

## 1. Product Vision
ForgeHub is a control plane for planning, governing, and executing software projects with AI agents.
It combines project management, version scope control, task orchestration, artifact governance, execution traceability, cost awareness, and independent validation into one operating model.

The product must behave as a central console for:
- registering products and product versions;
- creating projects linked to a target version;
- defining project plans and baselines;
- breaking planning items into tasks and subtasks;
- assigning tasks to agents;
- tracking executions, approvals, and artifacts;
- controlling pipeline stages and required deliverables;
- tracking bugs, features, and technical improvements;
- preserving auditability and decision traceability;
- preparing release readiness for product versions.

## 2. Product Objective
The objective of ForgeHub is to enable continuous software delivery with AI agents in a structured, traceable, and governable way.

Core rule:
> No feature, bug, task, skill, execution, or artifact may exist without linkage to product, version, project, planning, pipeline, owner, status, audit trail, and validation criteria.

## 3. Target Scope
The first release focuses on the Foundation MVP.

Included in Phase 1:
- product management;
- product modules;
- semantic versioning;
- project registration;
- project planning;
- plan baselines;
- change requests;
- pipeline templates;
- project pipelines;
- pipeline stages;
- required artifacts per stage;
- gates and approvals;
- agents and sub-agents;
- skills and skill permissions;
- planning items (feature, bug, improvement, technical debt, documentation, research);
- tasks and subtasks;
- task assignment and execution tracking;
- basic cost control;
- artifacts and artifact versions;
- audit events;
- initial seed data.

Out of scope for Phase 1:
- autonomous dispatch without approval;
- advanced critical path planning;
- Gantt dependencies with full resource optimization;
- marketplace mechanics for skills;
- unrestricted skill creation;
- automatic production deployment;
- advanced historical performance analytics.

## 4. Domain Model
The system should follow this core structure:

```txt
Product
 └── ProductVersion
      └── Project
           ├── ProjectPlan
           │    ├── PlanningItem
           │    │    ├── FeatureRequest
           │    │    ├── BugReport
           │    │    └── ProjectTask
           │    │         └── TaskExecution
           │    └── PlanBaseline
           └── ProjectPipeline
                └── PipelineStage
                     ├── RequiredArtifact
                     ├── Gate
                     ├── Task
                     └── Artifact
```

## 5. Key Concepts

### 5.1 Product
Represents the software product or platform under continuous development.

### 5.2 Product Version
Represents a planned, in-development, in-test, or published version of the product.
Example: 0.1.0 — Foundation MVP.

### 5.3 Project
Represents a bounded initiative associated with a product version.
Example: ForgeHub — Foundation MVP.

### 5.4 Project Plan
Represents scope, schedule, baseline, estimates, tasks, and execution planning.

### 5.5 Project Pipeline
Represents the delivery flow of the project.
Every project must have an active pipeline.

### 5.6 Pipeline Stage
Represents a stage in the delivery pipeline.
Examples: Discovery, PRD, SPEC, DATA SPEC, BUSINESS RULE SPEC, SECURITY SPEC, Architecture Review, Implementation, Migration, Testing, Build, Release Notes, Deployment Package, Release Approval.

### 5.7 Artifact
Represents any formal deliverable produced in the project.
Examples: PRD, SPEC, DATA SPEC, SECURITY SPEC, source code, migration, test report, release notes, pull request, deployment package, approval record.

### 5.8 Planning Item
Represents any item entering version planning.
Types: feature, bug, hotfix, improvement, technical debt, refactoring, security fix, research, documentation.

### 5.9 Project Task
Represents a planned task or subtask.
Subtasks use parent relationships.

### 5.10 Task Execution
Represents a real execution attempt by an agent, sub-agent, human, or system.

### 5.11 Agent
Represents an executor or coordinator agent.

### 5.12 Sub-Agent
Represents a subordinate agent with scoped permissions and skills.

### 5.13 Skill
Represents a versioned, governed capability with risk and permission boundaries.

## 6. Primary User Journeys

### 6.1 Feature Journey
1. Product Owner creates a FeatureRequest.
2. FeatureRequest becomes a PlanningItem.
3. PlanningItem enters version scope.
4. Tasks are created and assigned.
5. Agents execute tasks.
6. Artefacts are produced and validated.
7. Approval gates are satisfied.
8. The feature becomes eligible for release.

### 6.2 Bug Journey
1. BugReport is created with severity, environment, and detection version.
2. BugReport becomes a PlanningItem.
3. The bug is triaged.
4. Fix tasks are created and assigned.
5. The fix is implemented and validated.
6. Regression evidence is attached.
7. The bug is closed in the target fix version.

### 6.3 Pipeline Journey
1. Project starts with a pipeline template.
2. Stages are activated in sequence.
3. Required artifacts are produced and checked.
4. Gates are reviewed.
5. Release readiness is achieved only when all mandatory gates pass.

## 7. Delivery Principles
- Every project must have an active pipeline.
- Planning approved by baseline requires change requests for any post-baseline deviation.
- Planned, assigned, and executed states must remain distinct.
- Every execution must produce evidence.
- Every critical decision must be auditable.
- Every release must be backed by validation artifacts.
- No stage can complete without its required artifacts.

## 8. Definition of Done

### 8.1 Feature Done
A feature is done only when:
- linked tasks are complete;
- acceptance criteria are satisfied;
- required artifacts exist;
- tests are executed;
- review is approved;
- documentation is updated when applicable;
- target version or release is linked.

### 8.2 Bug Done
A bug is done only when:
- reproduction or justification is documented;
- root cause is recorded;
- fix is implemented;
- regression test exists;
- validation is complete;
- fixed_in_version is populated;
- evidence is attached.

### 8.3 Task Done
A task is done only when:
- execution is recorded;
- outcome is recorded;
- actual cost is tracked;
- evidence or artifact is attached;
- approval exists when required;
- audit event is created.

## 9. Strategic Outcome
ForgeHub must become the operating layer that gives teams and agents a disciplined path from planning to validated delivery.
It must prevent ad hoc execution, reduce ambiguity, and make every outcome traceable to a product version and a governed pipeline.
