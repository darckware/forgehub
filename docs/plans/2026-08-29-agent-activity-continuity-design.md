# Agent Activity and Cross-Runtime Continuity Design

**Status:** Approved design  
**Date:** 2026-08-29  
**Operator:** Marcelo  
**Primary interface:** ForgeHub  
**Orchestrator:** Athos  
**Selected visual direction:** [Continuity operational](https://superdesign.dev/teams/e0c6a6e8-9263-4e15-a19c-a314e0a622e1/projects/5c3ea9c0-d0dd-489a-9f6c-36c33873154a?node=draft-variant-85f71cfa-b2e5-4cb3-a89d-af05778598cf)

## 1. Purpose

Rebuild ForgeHub's Agent Activity page as the operational view of real teamwork across Hermes and external runtimes. The page must explain what each agent is doing, which project and task owns that work, which agent requested it, what the agent requested from others, what it is waiting for, which errors or approvals block progress, and how work can safely continue when a runtime becomes unavailable.

The design also standardizes assisted continuity among Porthus (Claude Code), Aramis (Codex CLI), and Dartan (Gemini CLI/Agy). Continuity is never automatic: Athos preserves and evaluates context, recommends compatible successors, and waits for Marcelo's decision.

## 2. Design principles

- Canonical records are authoritative; decorative animation is not state.
- ForgeHub remains a calm, professional mission-control ledger.
- The live communication map is the primary visual element, supported by dense textual evidence.
- Errors, blockers, authorization gates, and ownership changes are first-class records.
- One decision is synchronized across Agent Activity, Messages, and Notifications.
- External agents use runtime-native profile structures linked to Foundation; they are not fake internal Hermes profiles.
- High-risk, privileged, destructive, release, and deployment operations remain subject to explicit authority.

## 3. Canonical data ownership

| Concern | Authoritative source | Agent Activity responsibility |
| --- | --- | --- |
| Inter-agent requests and replies | Messages / `agent_demands` | Show sender, recipient, dispatch, reply relationship, response requirement, and wait state |
| Project and task ownership | Projects, project tasks, assignments, work packages | Show current project, task, assignment, runtime profile, and work contract |
| Execution state | Task executions, execution leases, execution events | Show active owner, runner health, attempt, runtime, and execution lifecycle |
| Recoverable progress | Progress checkpoints | Show last confirmed step, evidence, blocker/error code, state snapshot, and resume point |
| Authorization | Governance approval requests and decisions | Show requested action, approver, status, and decision; route actions to canonical governance commands |
| Operator attention | Notifications | Mirror synchronized incidents and decisions without creating an independent decision record |
| Runtime routing and health | ForgeRouter activity and runner telemetry | Add recent routing, limit, availability, and runtime evidence without replacing durable work state |
| Identity and operating character | Foundation contracts plus runtime-native profile files | Display profile health and provenance; do not duplicate or reinterpret authority |

Free-form message text may provide explanation but must not be parsed as the authoritative source for ownership, approval, checkpoint, or execution state when structured records exist.

## 4. Read model

Agent Activity should consume a purpose-built operational read model assembled by the backend. The read model may aggregate the canonical domains above but must not create a parallel workflow table.

The response should expose:

- agents with identity, runtime, availability, current project/task/execution, current action, latest checkpoint, and profile health;
- directed communication edges with message identifiers, sender, recipient, request/reply status, timestamps, and response waits;
- incidents with severity, code, source, affected records, age, impact, checkpoint, resume point, prior attempts, and recommended action;
- pending authorizations with governed approval identifiers and allowed decisions;
- continuity cases with interrupted owner, cause, preserved context, compatible successors, risk assessment, and decision state;
- timeline events with stable identifiers and links to their canonical records;
- freshness metadata per data source so the UI can represent partial degradation honestly.

The initial delivery may use bounded polling consistent with existing ForgeHub hooks. The contract should permit later server-sent events without changing the view model.

## 5. Page structure

The selected continuity-first design has four coordinated regions.

### 5.1 Operational topology

The largest region is a live map of agents and real communication relationships. Agent nodes show identity, runtime health, and compact current project/task context. Directed edges represent real Messages requests and replies. Node and edge selection opens structured details and links to canonical records.

Motion is limited to real dispatched messages and confirmed state transitions. Idle links do not animate. Reduced-motion users receive equivalent static indicators.

### 5.2 Severity inbox

A persistent rail summarizes and orders failed executions, heartbeat loss, runtime/quota limits, blockers, and pending authorizations by severity and elapsed time. Each incident exposes its code, source, project/task/execution, owner, checkpoint/resume information, and recommended next action.

The `Request Athos monitoring` action creates a traceable Messages request linked to the incident and affected execution. A confirmation shows exactly which context will be sent.

### 5.3 Selected-agent inspector

Selecting an agent reveals:

- identity, runtime, availability, profile/heartbeat health;
- current project, task, work package, action, branch, and working path where available;
- source task and sender;
- incoming and outgoing requests;
- responses or dependencies being awaited;
- latest checkpoint, evidence, verification, and resume point;
- errors, blockers, pending authorization, and proposed next action.

The inspector uses progressive disclosure and does not obscure the topology.

### 5.4 Continuity timeline

The lower timeline shows the chronological and cross-agent flow of requests, replies, checkpoints, interruptions, Athos evaluation, successor candidates, decisions, revalidation, and ownership transfer.

It must clearly distinguish:

- current ownership;
- proposed successor;
- `Awaiting Marcelo's decision`;
- approved transfer in progress;
- successor revalidation;
- completed ownership transfer.

## 6. Assisted continuity protocol

An interruption may be triggered by a runtime limit, unavailable provider, heartbeat loss, process failure, explicit pause, or a blocker that makes the current runtime unsuitable.

The protocol is:

1. Record or reconcile the latest recoverable checkpoint.
2. Preserve the current execution and ownership; do not silently reassign it.
3. Athos diagnoses the interruption and assembles a continuity package.
4. Athos ranks compatible candidates using capability, runtime availability, project authorization, current allocation, and context-loss risk.
5. ForgeHub presents the recommendation, alternatives, risks, missing information, and required approvals in Agent Activity, Messages, and Notifications.
6. ForgeHub displays `Awaiting Marcelo's decision` and performs no transfer.
7. Marcelo approves a candidate or chooses another action.
8. The decision is recorded once in the canonical workflow and reflected everywhere.
9. The successor acknowledges the continuity package and revalidates repository state, changed files, checkpoint evidence, and verification results.
10. Ownership changes only after successful revalidation; failures return the case to a visible blocked state.

## 7. Continuity package

The package contains:

- objective, scope, acceptance criteria, and definition of done;
- project, repository, branch, working directory, allowed paths, and denied paths;
- task, assignment, work package, execution, and prior owner identifiers;
- files changed, incomplete edits, relevant diff or artifact references;
- last confirmed checkpoint, completed requirements, evidence, and resume step;
- verification commands and their latest results;
- relevant Messages thread, decisions, requests, replies, and unresolved waits;
- errors, blockers, authorization requirements, retry history, and runtime health evidence;
- known risks, prohibited actions, budget/time constraints, and escalation path;
- recommended candidates, selected successor, Marcelo's decision, and decision timestamp.

Secrets, raw credentials, unrelated private conversation, and unbounded private runtime state are excluded.

## 8. External-agent profile contract

Porthus, Aramis, and Dartan retain equivalent operating layers adapted to each native runtime:

- identity and mission;
- operating character and principles;
- operator preferences;
- memory and recovery rules;
- tool map and authority boundaries;
- health/heartbeat contract;
- Foundation link and collective knowledge adapter.

Existing canonical and runtime-native files are audited and completed rather than duplicated. Agent Activity reports whether the expected layers are present and healthy, with provenance. It does not expose private memory contents or credentials.

## 9. Athos authority

Athos may:

- monitor an incident;
- request diagnosis, verification, or correction from another agent;
- assemble evidence and a continuity package;
- recommend and compare compatible successors;
- prepare a governed decision for Marcelo;
- escalate a stalled or risky case.

Without explicit authority, Athos may not:

- transfer ownership;
- approve its own request;
- execute privileged or destructive actions;
- deploy, publish, or release;
- expand the original task scope.

## 10. Interaction and accessibility

- Every graphical node and connection has a keyboard-accessible textual equivalent.
- Focus is visible and navigation order is predictable.
- Status is conveyed with text/icon in addition to color.
- Motion respects `prefers-reduced-motion`.
- Project, task, execution, message, checkpoint, incident, and approval identifiers link to canonical details.
- Filtering by project, agent, runtime, state, severity, sender, recipient, and time preserves selected context where possible.
- Loading, empty, stale, partially degraded, unavailable-source, and action-error states retain stable geometry and actionable copy.
- Mobile layouts stack the operational rail and use an accessible sheet/dialog for the inspector without removing information or decisions.

## 11. Error model

An incident record presented by Agent Activity includes:

- severity and stable error/blocker code;
- technical source and human-readable summary;
- occurrence and last-observed timestamps;
- affected project, task, execution, agent, runtime, and provider where applicable;
- last valid checkpoint and resume point;
- impact, recommended action, and current owner;
- prior attempts and outcomes;
- related Messages, Notifications, and approval references.

Partial source failures are themselves visible. The UI must not display a healthy aggregate when a required source is stale or unavailable.

## 12. Acceptance criteria

- The page identifies the current project, task, action, and owner for every active execution represented by canonical data.
- Requests, replies, senders, recipients, and waits shown on the topology match Messages records.
- Errors, blockers, heartbeat loss, runtime limits, and pending approvals are visible and link to their sources.
- Requesting Athos monitoring creates a traceable, incident-linked Messages record.
- A continuity case preserves its prior owner and shows `Awaiting Marcelo's decision` until a governed decision exists.
- No runtime transfer occurs automatically.
- A successor cannot take ownership before acknowledging and revalidating the continuity package.
- One decision is reflected consistently in Agent Activity, Messages, and Notifications.
- Porthus, Aramis, and Dartan profile-health reporting uses their native profile contracts and does not create fake Hermes profiles.
- The page meets keyboard, contrast, semantic-status, stable-layout, reduced-motion, loading, empty, error, and partial-degradation requirements.
- Backend and frontend tests cover read-model aggregation, permissions, idempotency, handoff state transitions, error paths, and primary UI interactions.

## 13. Non-goals

- Automatic agent reassignment.
- Replacing Messages, Notifications, Governance, Progress Checkpoints, or governed execution with a new parallel system.
- Parsing free-form agent prose as a substitute for structured operational state.
- Exposing private runtime memory or secrets.
- Granting Athos or external agents new approval authority through UI presentation alone.
