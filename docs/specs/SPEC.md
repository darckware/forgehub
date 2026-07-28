# ForgeHub — Software Specification (SPEC)

> **Status documental:** especificação original, preservada como histórico. Não é contrato suficiente para implementar a arquitetura-alvo atual. Use `PLANNING_DELIVERY_ARCHITECTURE.md`, `ENGINEERING_LOOP.md` e `IMPLEMENTATION_READINESS.md`, confirmando o comportamento disponível no código.

## 1. Scope
This document defines the functional and technical specification for ForgeHub, the control plane for product/version/project planning, task orchestration, execution tracking, and governance.

The implementation must align with the Hermes Foundation technology stack and governance rules, including the UI curation policy for complementary libraries.

## 2. Canonical Stack Constraints
The project must follow the Foundation stack:
- React 18+
- Vite
- TypeScript strict
- Tailwind CSS
- shadcn/ui
- Radix UI
- Lucide React
- Framer Motion when necessary
- clsx + tailwind-merge

Any UI library outside the canonical stack is considered complementary and governed by Foundation policy. If a library replaces the canonical stack, introduces a parallel design system, adds a significant runtime dependency, or uses premium/commercial licensing in production, an ADR is required before adoption.

## 3. Architecture Overview
ForgeHub should be implemented as a modular product with three primary layers:

### 3.1 Frontend
- React + Vite SPA
- TypeScript strict
- Tailwind CSS design system
- shadcn/ui for base components
- Radix UI for accessibility primitives
- Framer Motion only when motion improves UX and remains accessible

### 3.2 Backend
- C# / ASP.NET Core Web API
- Clean Architecture
- Modular Monolith in Phase 1
- Dapper for data access
- PostgreSQL as the source of truth

### 3.3 Data and Governance
- PostgreSQL for transactional storage
- audit events for traceability
- explicit approvals for gated transitions
- baseline and change request flow for scope control

## 4. Domain Model

### 4.1 Product Domain
Tables / entities:
- products
- product_modules
- product_versions
- releases

### 4.2 Project Domain
- projects
- project_plans
- plan_baselines
- change_requests

### 4.3 Pipeline Domain
- pipeline_templates
- pipeline_template_stages
- pipeline_template_required_artifacts
- project_pipelines
- pipeline_stages
- pipeline_stage_dependencies
- pipeline_stage_required_artifacts
- pipeline_stage_gates

### 4.4 Backlog Domain
- planning_items
- feature_requests
- bug_reports
- version_scope_items
- triage_decisions

### 4.5 Task Domain
- project_tasks
- task_dependencies
- task_required_skills
- task_assignments
- task_executions

### 4.6 Agent Domain
- agents
- sub_agents
- skills
- agent_skills
- sub_agent_skills
- agent_cost_rates
- agent_capacities

### 4.7 Artifact Domain
- artifacts
- artifact_versions

### 4.8 Governance Domain
- approvals
- audit_events
- policies

## 5. Functional Requirements

### 5.1 Product Management
- Create, update, and list products.
- Manage product modules.
- Maintain semantic versions.
- Prevent direct mutation of published versions.

### 5.2 Project Management
- Create projects linked to a product version.
- Create project plans and baselines.
- Register change requests after baseline freeze.

### 5.3 Pipeline Management
- Create pipeline templates.
- Create active project pipelines.
- Create stages and stage dependencies.
- Define required artifacts for each stage.
- Define gates requiring approval or verification.

### 5.4 Planning and Execution
- Capture planning items as feature, bug, improvement, technical debt, refactoring, security fix, research, or documentation.
- Split planning items into tasks and subtasks.
- Assign tasks to agents or sub-agents.
- Track each execution attempt separately.
- Allow multiple executions per task (failed, retried, verified, completed).

### 5.5 Agent and Skill Governance
- Register agents and sub-agents.
- Register skills with risk level, origin, and version.
- Associate skills with agents and sub-agents.
- Enforce explicit permission boundaries.

### 5.6 Artifact Governance
- Register artifacts and artifact versions.
- Link artifacts to task executions and pipeline stages.
- Block stage completion when required artifacts are missing.

### 5.7 Audit and Approval
- Record audit events for every major entity transition.
- Record approvals for gated steps.
- Preserve traceability from planning item to release.

## 6. Business Rules

### 6.1 Product Rules
1. Every product must have a unique name.
2. Every product can have many modules.
3. Every product must have at least one version.
4. Published versions cannot be mutated directly.
5. Fixes for published versions must create patch or hotfix flows.

### 6.2 Pipeline Rules
1. Every project must have an active pipeline.
2. Only one pipeline can be active per project.
3. Every stage must define order, status, and type.
4. Stages may require human approval.
5. Stages may require independent verification.
6. Stages may require mandatory artifacts.
7. A stage cannot complete if mandatory artifacts are missing.
8. A stage cannot complete if mandatory artifacts require approval and approval is missing.
9. Blocked stages must prevent dependent stages from advancing.
10. Release approval is allowed only when all required gates pass.

### 6.3 Planning Rules
1. Approved planning becomes baseline.
2. Post-baseline changes require a Change Request.
3. Change Requests must track scope, time, cost, feature additions/removals, critical bugs, agent changes, skill changes, architecture changes, and security changes.

### 6.4 Execution Rules
1. Planned, assigned, and executed must remain distinct states.
2. Each task can have multiple executions.
3. Every execution must have evidence.
4. Every task completion must be auditable.

### 6.5 Skill Rules
1. Every skill must have a version.
2. Every skill must have an origin.
3. Every skill must have a risk level.
4. Every skill must declare permissions.
5. Critical skills require approval.
6. Third-party skills require security review.
7. Sub-agents may only use skills that are explicit or inherited by permission.
8. Approved skills must not change without a new version.

## 7. UI Stack and Complementary Library Governance
The frontend must follow the Foundation technology stack policy and the UI curation policy for complementary libraries.

Key constraints:
- shadcn/ui remains the base UI composition layer.
- Radix UI remains the accessibility primitive layer.
- Tailwind CSS remains the styling standard.
- External UI libraries are references or accelerators, not architectural truth.
- Any adoption of a complementary library requires validation of license, accessibility, responsiveness, bundle impact, maintenance, security, and alignment to the design system.
- Premium or commercial libraries require explicit evaluation before production use.
- Experimental libraries require ADR before production use.
- WebGL, canvas, or intense animation libraries require additional performance and accessibility review.

## 8. Primary User Flows

### 8.1 Feature Flow
1. Create FeatureRequest.
2. Convert to PlanningItem.
3. Scope into a product version.
4. Break into tasks and subtasks.
5. Assign tasks to agents.
6. Execute and capture evidence.
7. Produce artifacts.
8. Validate and approve.
9. Mark release readiness.

### 8.2 Bug Flow
1. Create BugReport.
2. Triage severity and target fix version.
3. Convert to PlanningItem.
4. Break into corrective tasks.
5. Implement fix.
6. Run regression tests.
7. Attach validation evidence.
8. Close the bug in the target version.

### 8.3 Pipeline Flow
1. Create project and active pipeline.
2. Add stages and dependencies.
3. Create required artifacts and gates.
4. Execute tasks per stage.
5. Approve or reject gates.
6. Advance only when rules are satisfied.

## 9. Acceptance Criteria
The system is acceptable when:
- product/version/project traceability exists;
- planning items are represented before tasks;
- tasks have assignments and executions;
- stages enforce required artifacts and approvals;
- audit trail covers critical transitions;
- UI uses the canonical stack with governed complementary libraries only;
- release readiness can be validated from product version to artifact evidence.

## 10. Directory Layout
The project root is:
`/root/work/projects/dev/HermesForge`

Expected structure:

```txt
/root/work/projects/dev/HermesForge/
├── docs/
├── src/
│   ├── backend/
│   ├── frontend/
│   └── database/
├── scripts/
├── data/
└── reports/
```

## 11. Delivery Notes
- Implementation must be incremental and traceable.
- Any deviation from the canonical stack or pipeline rules requires an ADR.
- External UI libraries should be internalized when possible to avoid runtime lock-in.
- AI-generated UI must be reviewed for accessibility, responsiveness, consistency, and over-animation.

## 12. Next Spec Artifacts
After this SPEC, the next canonical artifacts are:
- DATA SPEC
- BUSINESS RULE SPEC
- SECURITY SPEC
- Task Breakdown
- Implementation Plan
- Validation Plan
